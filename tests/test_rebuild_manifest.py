from types import SimpleNamespace
import pytest

from synapse_dataset_manager.cli import generate_file_rebuild_manifest, _rebuild_versions
from synapse_dataset_manager.dataset_rebuild import index_file_rebuild_report, build_dataset_rebuild_draft, build_folder_rebuild_draft


class FakeSyn:
    def get(self, entity_id, downloadFile=False):
        assert downloadFile is False
        return SimpleNamespace(name='release.csv')

    def getChildren(self, folder):
        return [{'id': 'syn10', 'name': 'raw.csv',
                 'type': 'org.sagebionetworks.repo.model.FileEntity'}]

    def restGET(self, path):
        return {'results': [{'versionNumber': 1}, {'versionNumber': 2}]}


def test_file_generator_pins_latest_without_download():
    manifest = generate_file_rebuild_manifest(
        FakeSyn(), 'syn1', 'raw.csv', {'v1': 'syn20'}, 'syn30', False)
    assert manifest['targets'][0]['sources'][0]['source_version'] == 2
    assert manifest['targets'][0]['annotation_source_entity_id'] == 'syn1'


def test_missing_file_does_not_guess_noninteractive():
    with pytest.raises(ValueError, match='expected one exact match'):
        generate_file_rebuild_manifest(FakeSyn(), 'syn1', 'missing.csv',
                                       {'v1': 'syn20'}, 'syn30', False)


def test_report_index_uses_real_created_output():
    report = {'created': [{'originalEntityId': 'syn1', 'entityId': 'syn2',
                           'versions': [{'label': 'v1', 'versionNumber': 3}]}]}
    assert index_file_rebuild_report(report)[('syn1', 'v1')][0]['version'] == 3


def test_dataset_manifest_ambiguity_and_keep_are_explicit():
    versions = [{'label': 'v1', 'versionNumber': 1}, {'label': 'v1', 'versionNumber': 2}]
    report = {'status': 'completed', 'created': [{'originalEntityId': 'syn1', 'entityId': 'syn2', 'versions': versions}]}
    snapshots = [{'versionNumber': 1, 'versionLabel': 'v1', 'members': [
        {'id': 'syn1', 'version': 1, 'versionLabel': 'v1'}]}]
    with pytest.raises(ValueError, match='Ambiguous'):
        build_dataset_rebuild_draft(snapshots, report, interactive=False)
    draft = build_dataset_rebuild_draft(snapshots, report, input_fn=lambda _: '2')
    assert draft['releases'][0]['member_replacements']['syn1']['version'] == 2
    draft = build_dataset_rebuild_draft(snapshots, report, input_fn=lambda _: 'k')
    assert draft['releases'][0]['member_replacements'] == {}


def test_folder_match_exact_name_and_label():
    snapshots = [{'versionNumber': 1, 'versionLabel': 'v1', 'members': [
        {'id': 'syn1', 'name': 'release.csv', 'version': 1, 'versionLabel': 'v1'},
        {'id': 'syn3', 'name': 'other.csv', 'version': 2, 'versionLabel': 'v1'}]}]
    files = [{'id': 'syn2', 'name': 'release.csv',
              'versions': [{'versionNumber': 3, 'versionLabel': 'v1'}]}]
    with pytest.raises(ValueError, match='Ambiguous or missing'):
        build_folder_rebuild_draft(snapshots, files, interactive=False)
    answers = iter(['1', 'k'])
    draft = build_folder_rebuild_draft(snapshots, files, input_fn=lambda _: next(answers))
    assert draft['releases'][0]['member_replacements']['syn1']['version'] == 3
    assert draft['releases'][0]['kept_members'] == [
        {'id': 'syn3', 'version': 2, 'reason': 'explicit interactive keep'}]


def test_folder_renamed_file_requires_explicit_keep():
    snapshots = [{'versionNumber': 1, 'versionLabel': 'v1', 'members': [
        {'id': 'syn1', 'name': 'old.csv', 'version': 1, 'versionLabel': 'v1'}]}]
    files = [{'id': 'syn2', 'name': 'renamed.csv',
              'versions': [{'versionNumber': 2, 'versionLabel': 'v1'}]}]
    with pytest.raises(ValueError, match='Ambiguous or missing'):
        build_folder_rebuild_draft(snapshots, files, interactive=False)
    assert build_folder_rebuild_draft(snapshots, files, input_fn=lambda _: 'k')['releases'][0]['kept_members'][0]['id'] == 'syn1'


def test_incomplete_report_is_not_accepted_for_dataset_manifest():
    with pytest.raises(ValueError, match='incomplete'):
        build_dataset_rebuild_draft([], {'status': 'failed', 'created': []}, interactive=False)


def test_version_pagination():
    class Pages:
        def restGET(self, path):
            if 'offset=0' in path:
                return {'results': [{'versionNumber': i} for i in range(100)]}
            return {'results': [{'versionNumber': 100}]}
    assert len(_rebuild_versions(Pages(), 'syn1')) == 101


def test_explicit_snapshot_replacements_skip_unavailable_members(tmp_path, monkeypatch):
    import json
    from synapse_dataset_manager import cli

    calls = []
    class Syn:
        def login(self, **kwargs):
            pass

        def get_annotations(self, entity_id, version=None):
            return {}

        def get(self, entity_id, version=None, downloadFile=False):
            calls.append((entity_id, version, downloadFile))
            return {'concreteType': 'org.sagebionetworks.repo.model.FileEntity',
                    'name': 'retained', 'versionLabel': 'v1'}

    class Dataset:
        def __init__(self, id, version_number):
            self.version = version_number

        def get(self, synapse_client):
            return SimpleNamespace(items=[SimpleNamespace(id='syn1', version=1),
                                          SimpleNamespace(id='syn3', version=1),
                                          SimpleNamespace(id='syn4', version=2)],
                                   version_label=f'v{self.version}', version_comment='')

    monkeypatch.setattr(cli.synapseclient, 'Synapse', Syn)
    monkeypatch.setattr(cli, 'Dataset', Dataset)
    monkeypatch.setattr(cli, '_rebuild_versions', lambda syn, id: [{'versionNumber': 1}, {'versionNumber': 2}])
    args = SimpleNamespace(source_dataset='syn100', file_rebuild_report=None,
                           replacement_folder=None, output_name='new', output=str(tmp_path / 'draft.json'),
                           non_interactive=True, exclude_member=['syn3'],
                           replace_member=['1:syn1=syn2:3', '2:syn1=syn2:4'])
    cli.handle_generate_dataset_rebuild_manifest(args, None)
    draft = json.loads((tmp_path / 'draft.json').read_text())
    assert [r['member_replacements']['syn1']['version'] for r in draft['releases']] == [3, 4]
    assert all(r['member_removals'] == ['syn3'] for r in draft['releases'])
    assert ('syn4', 2, False) in calls
    assert not any(entity_id in ('syn1', 'syn3') for entity_id, _, _ in calls)
    assert all(download is False for _, _, download in calls)

    args.replace_member = ['1:syn1=syn4:3']
    with pytest.raises(ValueError, match='Duplicate replacement'):
        cli.handle_generate_dataset_rebuild_manifest(args, None)
    args.replace_member = ['3:syn1=syn2:3']
    with pytest.raises(ValueError, match='absent'):
        cli.handle_generate_dataset_rebuild_manifest(args, None)
    args.replace_member = ['1:syn1=syn2:0']
    with pytest.raises(ValueError, match='positive versions'):
        cli.handle_generate_dataset_rebuild_manifest(args, None)
    args.replace_member = ['1:syn3=syn2:1']
    with pytest.raises(ValueError, match='both excluded'):
        cli.handle_generate_dataset_rebuild_manifest(args, None)


def test_dataset_generator_source_version_selection(tmp_path, monkeypatch):
    import json
    from synapse_dataset_manager import cli

    fetched = []

    class Syn:
        def login(self, **kwargs):
            pass

        def get_annotations(self, entity_id, version=None):
            return {}

        def get(self, entity_id, version=None, downloadFile=False):
            assert downloadFile is False
            return {'concreteType': 'org.sagebionetworks.repo.model.FileEntity'}

    class Dataset:
        def __init__(self, id, version_number):
            self.version = version_number

        def get(self, synapse_client):
            fetched.append(self.version)
            return SimpleNamespace(items=[SimpleNamespace(id='syn1', version=1)],
                                   version_label=f'v{self.version}', version_comment='')

    monkeypatch.setattr(cli.synapseclient, 'Synapse', Syn)
    monkeypatch.setattr(cli, 'Dataset', Dataset)
    monkeypatch.setattr(cli, '_rebuild_versions', lambda syn, id: [
        {'versionNumber': 3}, {'versionNumber': 2}, {'versionNumber': 1}])
    args = SimpleNamespace(source_dataset='syn100', file_rebuild_report=None,
                           replacement_folder=None, output_name='new', output=str(tmp_path / 'draft.json'),
                           non_interactive=True, exclude_member=[], source_version=[3, 1],
                           replace_member=['1:syn1=syn2:1', '3:syn1=syn2:3'])
    cli.handle_generate_dataset_rebuild_manifest(args, None)
    draft = json.loads((tmp_path / 'draft.json').read_text())
    assert fetched == [1, 2, 3]
    assert [v['version'] for v in draft['source_baseline']] == [1, 2, 3]
    assert [r['source_dataset_version'] for r in draft['releases']] == [1, 3]
    assert [r['member_replacements']['syn1']['version'] for r in draft['releases']] == [1, 3]

    fetched.clear()
    args.source_version = [1, 4]
    with pytest.raises(ValueError, match=r'versions do not exist: \[4\]'):
        cli.handle_generate_dataset_rebuild_manifest(args, None)
    assert fetched == []
    for invalid in (0, -1):
        args.source_version = [invalid]
        with pytest.raises(ValueError, match='positive integer'):
            cli.handle_generate_dataset_rebuild_manifest(args, None)
    args.source_version = [1]
    with pytest.raises(ValueError, match='Explicit replacements absent'):
        cli.handle_generate_dataset_rebuild_manifest(args, None)


def test_folder_single_candidate_requires_review_and_shows_evidence(capsys):
    snapshots = [{'versionNumber': 1, 'versionLabel': 'v1', 'members': [
        {'id': 'syn1', 'name': 'a', 'version': 1, 'versionLabel': 'v1',
         'modifiedOn': '2020-01-01', 'versionComment': 'old'}]}]
    files = [{'id': 'syn2', 'name': 'a', 'versions': [
        {'versionNumber': 2, 'versionLabel': 'v1', 'modifiedOn': '2024-01-01',
         'versionComment': 'new'}]}]
    with pytest.raises(ValueError):
        build_folder_rebuild_draft(snapshots, files, interactive=False)
    result = build_folder_rebuild_draft(snapshots, files, input_fn=lambda _: '1')
    assert result['releases'][0]['member_replacements']['syn1']['version'] == 2
    text = capsys.readouterr().out
    assert '2020-01-01' in text and '2024-01-01' in text and 'old' in text and 'new' in text


def test_dataset_generator_rejects_snapshot_added_during_baseline(tmp_path, monkeypatch):
    from synapse_dataset_manager import cli

    class Syn:
        def login(self, **kwargs):
            pass

        def get_annotations(self, entity_id, version=None):
            return {}

    class Dataset:
        def __init__(self, id, version_number):
            self.version = version_number

        def get(self, synapse_client):
            return SimpleNamespace(items=[SimpleNamespace(id='syn1', version=1)],
                                   version_label=f'v{self.version}', version_comment='')

    listings = iter([[{'versionNumber': 1}],
                     [{'versionNumber': 1}, {'versionNumber': 2}]])
    monkeypatch.setattr(cli.synapseclient, 'Synapse', Syn)
    monkeypatch.setattr(cli, 'Dataset', Dataset)
    monkeypatch.setattr(cli, '_rebuild_versions', lambda syn, entity_id: next(listings))
    output = tmp_path / 'draft.json'
    args = SimpleNamespace(source_dataset='syn100', file_rebuild_report=None,
                           replacement_folder=None, output_name='new', output=str(output),
                           non_interactive=True, exclude_member=[],
                           replace_member=['1:syn1=syn2:1'])
    with pytest.raises(ValueError, match='versions changed during manifest generation'):
        cli.handle_generate_dataset_rebuild_manifest(args, None)
    assert not output.exists()
