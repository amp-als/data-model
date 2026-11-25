from types import SimpleNamespace

import pytest

from synapse_dataset_manager import cli


class FakeDataset:
    def __init__(self, id, version_number=None):
        self.version_number = version_number

    def get(self, synapse_client):
        if self.version_number is None:
            return SimpleNamespace(parent_id='synProject', columns={'name': object()})
        return SimpleNamespace(
            items=[SimpleNamespace(id='synOld', version=1),
                   SimpleNamespace(id='synKeep', version=2)],
            version_comment='source comment', annotations={'wrong': ['latest']})


class FakeSyn:
    def __init__(self):
        self.annotation_requests = []

    def get(self, entity_id, version=None, downloadFile=False):
        assert downloadFile is False
        if entity_id == 'synProject':
            return {'concreteType': 'org.sagebionetworks.repo.model.Project'}
        return {'concreteType': 'org.sagebionetworks.repo.model.FileEntity'}

    def get_annotations(self, entity_id, version=None):
        self.annotation_requests.append((entity_id, version))
        return {'sourceVersion': [str(version)]}

    def getWikiHeaders(self, entity_id):
        return []


def manifest(replacements=None):
    return {'source_dataset_id': 'synSource', 'output_name': 'new', 'releases': [
        {'source_dataset_version': 3, 'label': 'v3',
         'member_replacements': replacements or {},
         'annotation_overrides': {'reviewed': ['yes']}}]}


def test_preview_uses_version_annotations_and_pinned_members(monkeypatch):
    monkeypatch.setattr(cli, 'Dataset', FakeDataset)
    syn = FakeSyn()
    plan = cli.plan_dataset_rebuild(syn, manifest({'synOld': {'id': 'synNew', 'version': 4}}))
    release = plan['releases'][0]
    assert syn.annotation_requests == [('synSource', 3)]
    assert release['annotations'] == {'sourceVersion': ['3'], 'reviewed': ['yes']}
    assert release['members'] == {'synNew': 4, 'synKeep': 2}
    assert release['comment'] == 'source comment'


@pytest.mark.parametrize('version', [None, 0, True, '1'])
def test_preview_rejects_unpinned_replacements(monkeypatch, version):
    monkeypatch.setattr(cli, 'Dataset', FakeDataset)
    with pytest.raises(ValueError, match='positive pinned version'):
        cli.plan_dataset_rebuild(FakeSyn(), manifest({'synOld': {'id': 'synNew', 'version': version}}))


def test_preview_applies_substitutions_simultaneously(monkeypatch):
    monkeypatch.setattr(cli, 'Dataset', FakeDataset)
    plan = cli.plan_dataset_rebuild(FakeSyn(), manifest({
        'synOld': {'id': 'synKeep', 'version': 4},
        'synKeep': {'id': 'synNew', 'version': 5}}))
    assert plan['releases'][0]['members'] == {'synKeep': 4, 'synNew': 5}


def test_explicit_member_removal(monkeypatch):
    monkeypatch.setattr(cli, 'Dataset', FakeDataset)
    draft = manifest()
    draft['releases'][0]['member_removals'] = ['synOld']
    assert cli.plan_dataset_rebuild(FakeSyn(), draft)['releases'][0]['members'] == {'synKeep': 2}
    draft['releases'][0]['member_removals'] = ['synMissing']
    with pytest.raises(ValueError, match='absent'):
        cli.plan_dataset_rebuild(FakeSyn(), draft)


def test_explicit_pinned_member_addition(monkeypatch):
    monkeypatch.setattr(cli, 'Dataset', FakeDataset)
    draft = manifest()
    draft['releases'][0]['member_additions'] = [{'id': 'synDictionary', 'version': 5}]
    assert cli.plan_dataset_rebuild(FakeSyn(), draft)['releases'][0]['members']['synDictionary'] == 5


@pytest.mark.parametrize('addition', [{'id': 'synKeep', 'version': 5},
                                      {'id': 'synDictionary', 'version': True}])
def test_invalid_member_additions_rejected(monkeypatch, addition):
    monkeypatch.setattr(cli, 'Dataset', FakeDataset)
    draft = manifest()
    draft['releases'][0]['member_additions'] = [addition]
    with pytest.raises(ValueError):
        cli.plan_dataset_rebuild(FakeSyn(), draft)


def test_execute_fails_before_reading_manifest_or_logging_in():
    with pytest.raises(ValueError, match='--output is required'):
        cli.handle_rebuild_dataset_entity(SimpleNamespace(execute=True, output=None), None)


def test_preview_rejects_unavailable_retained_version(monkeypatch):
    monkeypatch.setattr(cli, 'Dataset', FakeDataset)

    class MissingVersionSyn(FakeSyn):
        def get(self, entity_id, version=None, downloadFile=False):
            assert downloadFile is False
            if (entity_id, version) == ('synKeep', 2):
                raise RuntimeError('version does not exist')
            return super().get(entity_id, version=version, downloadFile=downloadFile)

    with pytest.raises(ValueError, match='Retained member synKeep version 2 could not be read'):
        cli.plan_dataset_rebuild(MissingVersionSyn(), manifest({'synOld': {'id': 'synNew', 'version': 4}}))


def test_preview_caches_versions_and_skips_removed_and_replaced_originals(monkeypatch):
    monkeypatch.setattr(cli, 'Dataset', FakeDataset)

    class TrackingSyn(FakeSyn):
        def __init__(self):
            super().__init__()
            self.requests = []

        def get(self, entity_id, version=None, downloadFile=False):
            self.requests.append((entity_id, version, downloadFile))
            assert entity_id != 'synOld'
            return super().get(entity_id, version=version, downloadFile=downloadFile)

    draft = manifest({'synOld': {'id': 'synNew', 'version': 4}})
    draft['releases'].append({'source_dataset_version': 4, 'label': 'v4',
                              'member_removals': ['synOld'],
                              'member_additions': [{'id': 'synNew', 'version': 4}]})
    syn = TrackingSyn()
    cli.plan_dataset_rebuild(syn, draft)
    assert syn.requests.count(('synKeep', 2, False)) == 1
    assert syn.requests.count(('synNew', 4, False)) == 1
    assert all(download is False for _, _, download in syn.requests)


def test_execution_rejects_full_baseline_drift_before_mutation(monkeypatch, tmp_path):
    import json
    draft = manifest()
    draft['source_baseline'] = [{'version': 1}]
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(draft))
    class Syn:
        def login(self, **kwargs):
            pass
    monkeypatch.setattr(cli.synapseclient, 'Synapse', Syn)
    monkeypatch.setattr(cli, 'plan_dataset_rebuild', lambda syn, manifest: {})
    monkeypatch.setattr(cli, '_dataset_snapshot_baseline', lambda syn, source: [{'version': 2}])
    with pytest.raises(ValueError, match='baseline changed'):
        cli.handle_rebuild_dataset_entity(SimpleNamespace(execute=True, output=str(tmp_path / 'result'),
                                                          manifest=str(path)), None)
    assert not (tmp_path / 'result').exists()


def test_execution_does_not_overwrite_recovery_report(monkeypatch, tmp_path):
    import json
    path = tmp_path / 'manifest.json'
    draft = manifest()
    draft['source_baseline'] = []
    path.write_text(json.dumps(draft))
    output = tmp_path / 'result'
    output.write_text('previous partial report')
    class Syn:
        def login(self, **kwargs):
            pass
    monkeypatch.setattr(cli.synapseclient, 'Synapse', Syn)
    monkeypatch.setattr(cli, 'plan_dataset_rebuild', lambda syn, manifest: {
        'source_dataset_id': 'synSource', 'output_name': 'new'})
    monkeypatch.setattr(cli, '_dataset_snapshot_baseline', lambda syn, source: [])
    with pytest.raises(FileExistsError):
        cli.handle_rebuild_dataset_entity(SimpleNamespace(execute=True, output=str(output),
                                                          manifest=str(path)), None)
    assert output.read_text() == 'previous partial report'


def test_preview_does_not_overwrite_recovery_report(monkeypatch, tmp_path):
    import json
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(manifest()))
    output = tmp_path / 'result'
    output.write_text('previous partial report')

    class Syn:
        def login(self, **kwargs):
            pass

    monkeypatch.setattr(cli.synapseclient, 'Synapse', Syn)
    monkeypatch.setattr(cli, 'plan_dataset_rebuild',
                        lambda syn, manifest: {'releases': [], 'output_parent_id': 'synProject'})
    with pytest.raises(FileExistsError):
        cli.handle_rebuild_dataset_entity(SimpleNamespace(execute=False, output=str(output),
                                                          manifest=str(path)), None)
    assert output.read_text() == 'previous partial report'
