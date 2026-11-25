import json
from types import SimpleNamespace

import pytest

from synapse_dataset_manager import cli


class FakeSyn:
    def __init__(self):
        self.downloads = []

    def login(self, silent):
        pass

    def getChildren(self, folder):
        return [{'id': 'synSource', 'name': 'raw.csv',
                 'type': 'org.sagebionetworks.repo.model.FileEntity'}]

    def restGET(self, path):
        return {'results': [{'versionNumber': 1}]}

    def get(self, entity_id, **kwargs):
        # Simulate the SDK result; no file bytes are downloaded in tests.
        self.downloads.append((entity_id, kwargs))
        return SimpleNamespace(path='/fake/source')

    def get_annotations(self, entity_id, version):
        return {'copied': ['value']}


def manifest():
    return {'output_folder': 'synFolder', 'dataset_id': 'synDataset', 'targets': [{
        'key': 'one', 'output_name': 'same.csv', 'source_filename': 'raw.csv',
        'original_entity_id': 'synOriginal', 'annotation_source_entity_id': 'synAnnotations',
        'sources': [{'folder_id': 'synStaging', 'label': 'v1'},
                    {'folder_id': 'synStaging', 'label': 'v2'}]}]}


def setup(monkeypatch, tmp_path, data=None, execute=True):
    source = tmp_path / 'manifest.json'
    source.write_text(json.dumps(data or manifest()))
    syn = FakeSyn()
    monkeypatch.setattr(cli.synapseclient, 'Synapse', lambda: syn)
    args = SimpleNamespace(manifest=str(source), output=str(tmp_path / 'report.json'),
                           execute=execute, annotation_mode='automatic')
    return syn, args


def test_preview_uses_explicit_original_not_annotation_source(monkeypatch, tmp_path):
    syn, args = setup(monkeypatch, tmp_path, execute=False)
    report = cli.handle_rebuild_file_entity(args, None)
    assert report['targets'][0]['originalEntityId'] == 'synOriginal'
    assert not syn.downloads


@pytest.mark.parametrize('collision_id', ['synOriginal', 'synUnrelated'])
def test_existing_name_collisions_do_not_update_files(monkeypatch, tmp_path, collision_id):
    syn, args = setup(monkeypatch, tmp_path)
    calls = []
    class File:
        def __init__(self, **kwargs):
            calls.append(kwargs)
        def store(self, synapse_client):
            assert synapse_client is syn
            assert calls[-1]['create_or_update'] is False
            raise ValueError(f'Name collision with {collision_id}')
    monkeypatch.setattr(cli, 'File', File)
    monkeypatch.setattr(cli, 'Dataset', lambda *a, **kw: pytest.fail('Dataset must not be used'))
    with pytest.raises(ValueError, match='collision'):
        cli.handle_rebuild_file_entity(args, None)
    assert len(calls) == 1
    report = json.loads((tmp_path / 'report.json').read_text())
    assert report['status'] == 'failed'
    assert report['created'][0]['entityId'] is None
    assert 'outcome may be unknown' in report['phase']


def test_partial_version_failure_keeps_mapping_and_never_modifies_dataset(monkeypatch, tmp_path):
    syn, args = setup(monkeypatch, tmp_path)
    calls = []
    class File:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            calls.append(kwargs)
        def store(self, synapse_client):
            assert synapse_client is syn
            if len(calls) == 1:
                assert self.kwargs['create_or_update'] is False
                return SimpleNamespace(id='synReplacement', version_number=1)
            assert self.kwargs['id'] == 'synReplacement'
            raise TimeoutError('upload outcome unknown')
    monkeypatch.setattr(cli, 'File', File)
    monkeypatch.setattr(cli, 'Dataset', lambda *a, **kw: pytest.fail('Dataset must not be used'))
    with pytest.raises(TimeoutError):
        cli.handle_rebuild_file_entity(args, None)
    report = json.loads((tmp_path / 'report.json').read_text())
    assert report['status'] == 'failed'
    assert report['created'][0]['entityId'] == 'synReplacement'
    assert report['created'][0]['versions'][0]['versionNumber'] == 1
    assert 'outcome may be unknown' in report['phase']


def test_success_ignores_dataset_and_reports_all_versions(monkeypatch, tmp_path):
    syn, args = setup(monkeypatch, tmp_path)
    class File:
        count = 0
        def __init__(self, **kwargs):
            self.kwargs = kwargs
        def store(self, synapse_client):
            File.count += 1
            return SimpleNamespace(id='synReplacement', version_number=File.count)
    monkeypatch.setattr(cli, 'File', File)
    monkeypatch.setattr(cli, 'Dataset', lambda *a, **kw: pytest.fail('Dataset must not be used'))
    report = cli.handle_rebuild_file_entity(args, None)
    assert report['status'] == 'completed'
    assert [v['versionNumber'] for v in report['created'][0]['versions']] == [1, 2]
    assert json.loads((tmp_path / 'report.json').read_text())['status'] == 'completed'


def test_execution_requires_report_before_login(monkeypatch):
    monkeypatch.setattr(cli.synapseclient, 'Synapse', lambda: pytest.fail('must not log in'))
    with pytest.raises(ValueError, match='--output is required'):
        cli.handle_rebuild_file_entity(SimpleNamespace(execute=True, output=None), None)


def test_later_target_download_failure_keeps_first_target_report(monkeypatch, tmp_path):
    data = manifest()
    data['targets'][0]['sources'] = data['targets'][0]['sources'][:1]
    other = dict(data['targets'][0], key='two', output_name='other.csv')
    data['targets'].append(other)
    syn, args = setup(monkeypatch, tmp_path, data)
    original_get = syn.get
    def get(entity_id, **kwargs):
        if syn.downloads:
            raise OSError('download failed')
        return original_get(entity_id, **kwargs)
    syn.get = get
    class File:
        def __init__(self, **kwargs):
            pass
        def store(self, synapse_client):
            return SimpleNamespace(id='synReplacement', version_number=1)
    monkeypatch.setattr(cli, 'File', File)
    with pytest.raises(OSError, match='download failed'):
        cli.handle_rebuild_file_entity(args, None)
    report = json.loads((tmp_path / 'report.json').read_text())
    assert report['status'] == 'failed'
    assert report['created'][0]['entityId'] == 'synReplacement'
    assert report['created'][0]['versions'][0]['label'] == 'v1'
    assert report['phase'] == 'preparing two v1'


def test_file_preview_does_not_overwrite_recovery_report(monkeypatch, tmp_path):
    syn, args = setup(monkeypatch, tmp_path, execute=False)
    output = tmp_path / 'report.json'
    output.write_text('previous partial report')
    with pytest.raises(FileExistsError):
        cli.handle_rebuild_file_entity(args, None)
    assert output.read_text() == 'previous partial report'
    assert not syn.downloads


def test_competing_file_executions_reserve_report_before_download(monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    syn, args = setup(monkeypatch, tmp_path)
    entered, release = Event(), Event()
    calls = []

    def blocked_get(entity_id, **kwargs):
        calls.append(entity_id)
        entered.set()
        assert release.wait(5)
        raise TimeoutError('mock download failed')

    syn.get = blocked_get
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(cli.handle_rebuild_file_entity, args, None)
        try:
            assert entered.wait(5)
            second = pool.submit(cli.handle_rebuild_file_entity, args, None)
            with pytest.raises(FileExistsError):
                second.result(timeout=5)
        finally:
            release.set()
        with pytest.raises(TimeoutError):
            first.result(timeout=5)
    assert calls == ['synSource']
    report = json.loads((tmp_path / 'report.json').read_text())
    assert report['status'] == 'failed'
    assert report['phase'] == 'preparing one v1'
