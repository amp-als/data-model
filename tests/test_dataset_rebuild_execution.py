import json
from copy import deepcopy
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from synapse_dataset_manager.dataset_rebuild import dataset_schema, execute_dataset_rebuild


@dataclass
class Column:
    name: str
    column_type: str
    maximum_size: int


@dataclass
class Ref:
    id: str
    version: int


class Dataset:
    states = {}
    snapshots = {}

    def __init__(self, id=None, version_number=None):
        self.id, self.version_number = id, version_number

    def get(self, synapse_client):
        state = self.snapshots[(self.id, self.version_number)] if self.version_number else self.states[self.id]
        self.__dict__.update(deepcopy(state))
        return self

    def store(self, synapse_client):
        assert self.id == 'synNew'
        assert self.include_default_columns is False
        self.states[self.id] = deepcopy(self.__dict__)
        return self

    def snapshot(self, label, comment, synapse_client):
        version = 7 + len(self.snapshots)
        state = deepcopy(self.states[self.id])
        state.update(version_label=label, version_comment=comment)
        self.snapshots[(self.id, version)] = state
        return SimpleNamespace(snapshot_version_number=version)


class Syn:
    def __init__(self):
        self.created = 0

    def restPOST(self, path, body):
        assert path == '/entity'
        assert json.loads(body)['parentId'] == 'synProject'
        assert json.loads(body)['description'] == 'source description'
        self.created += 1
        Dataset.states['synNew'] = {'id': 'synNew', 'columns': {}, 'items': [], 'annotations': {}}
        return {'id': 'synNew'}

    def get_annotations(self, entity_id, version):
        return Dataset.snapshots[(entity_id, version)]['annotations']


@pytest.fixture
def context():
    columns = {'x': Column('x', 'STRING', 17)}
    Dataset.states = {'synSource': {'id': 'synSource', 'columns': columns}}
    Dataset.snapshots = {}
    plan = {'source_dataset_id': 'synSource', 'output_name': 'new',
            'output_parent_id': 'synProject', 'description': 'source description',
            'wiki_pages': [], 'schema': dataset_schema(columns),
            'releases': [
                {'source_dataset_version': 1, 'label': 'v1', 'comment': 'one',
                 'members': {'synFile': 1}, 'annotations': {'first': ['one']}},
                {'source_dataset_version': 2, 'label': 'v2', 'comment': 'two',
                 'members': {'synOther': 3}, 'annotations': {'second': ['two']}}]}
    return Syn(), plan


def test_execute_snapshots_are_verified_and_isolated(context, tmp_path):
    syn, plan = context
    output = tmp_path / 'result.json'
    report = execute_dataset_rebuild(syn, plan, output, Dataset, Ref, dict)
    assert report['status'] == 'completed'
    assert [r['version'] for r in report['releases']] == [7, 8]
    assert Dataset.snapshots[('synNew', 8)]['annotations'] == {'second': ['two']}
    assert Dataset.snapshots[('synNew', 8)]['items'] == [Ref('synOther', 3)]
    assert json.loads(output.read_text())['releases'][1]['status'] == 'verified'
    assert syn.created == 1


def test_wiki_attachments_warn_and_mark_for_manual_copy(context, tmp_path, capsys):
    syn, plan = context
    plan['wiki_pages'] = [{'id': '1'}]
    source = {'id': '1', 'title': 'Root', 'markdown': 'image',
              'attachmentFileHandleIds': ['123']}
    copied = {'id': '10', 'title': 'Root', 'markdown': 'image', 'parentWikiId': None}
    syn.getWiki = lambda owner, subpageId: source if owner == 'synSource' else copied
    syn.getWikiAttachments = lambda page: ([{'id': '123', 'fileName': 'image.png'}]
                                            if page is source else [])
    syn.store = lambda page: copied
    output = tmp_path / 'result.json'
    report = execute_dataset_rebuild(syn, plan, output, Dataset, Ref, dict)
    assert syn.created == 1
    assert 'reattach them manually' in capsys.readouterr().out.lower()
    assert report['wiki']['pages'][0]['uncopied_attachment_ids'] == ['123']
    assert report['wiki']['pages'][0]['uncopied_attachments'][0]['name'] == 'image.png'
    assert 'manual' in json.loads(output.read_text())['wiki']['status']


def test_verification_failure_reports_partial_and_stops(context, tmp_path):
    syn, plan = context
    syn.get_annotations = lambda entity_id, version: {'incorrect': ['value']}
    output = tmp_path / 'result.json'
    with pytest.raises(ValueError, match='verification failed'):
        execute_dataset_rebuild(syn, plan, output, Dataset, Ref, dict)
    report = json.loads(output.read_text())
    assert report['dataset_id'] == 'synNew'
    assert report['releases'][0]['version'] == 7
    assert report['releases'][0]['checks']['annotations'] is False
    assert len(report['releases']) == 1


def test_wiki_tree_copy_and_links(context, tmp_path):
    syn, plan = context
    plan['wiki_pages'] = [{'id': '2', 'parentId': '1'}, {'id': '1'}]
    source_pages = {
        '1': {'id': '1', 'title': 'Root', 'markdown': 'See syn123', 'parentWikiId': None},
        '2': {'id': '2', 'title': 'Child', 'markdown': 'child', 'parentWikiId': '1'}}
    stored = {}
    def get_wiki(owner, subpageId):
        return source_pages[subpageId] if owner == 'synSource' else stored[subpageId]
    def store(page):
        new_id = str(10 + len(stored))
        stored[new_id] = {'id': new_id, 'title': page['title'], 'markdown': page['markdown'],
                          'parentWikiId': page['parentWikiId']}
        return stored[new_id]
    syn.getWiki = get_wiki
    syn.getWikiAttachments = lambda page: []
    syn.store = store
    report = execute_dataset_rebuild(syn, plan, tmp_path / 'result.json', Dataset, Ref, dict)
    pages = report['wiki']['pages']
    assert [(p['source_id'], p['new_id']) for p in pages] == [('1', '10'), ('2', '11')]
    assert pages[0]['synapse_links'] == ['syn123']
    assert stored['11']['parentWikiId'] == '10'
    assert report['wiki']['status'] == 'verified'


def test_invalid_wiki_hierarchy_fails_before_creation(context, tmp_path):
    syn, plan = context
    plan['wiki_pages'] = [{'id': '2', 'parentId': 'missing'}]
    with pytest.raises(ValueError, match='missing parent or cycle'):
        execute_dataset_rebuild(syn, plan, tmp_path / 'result.json', Dataset, Ref, dict)
    assert syn.created == 0


def test_source_schema_drift_fails_before_creation(context, tmp_path):
    syn, plan = context
    Dataset.states['synSource']['columns']['x'].maximum_size = 18
    with pytest.raises(ValueError, match='Source schema changed'):
        execute_dataset_rebuild(syn, plan, tmp_path / 'result.json', Dataset, Ref, dict)
    assert syn.created == 0


def test_create_timeout_reports_uncertain_outcome(context, tmp_path):
    syn, plan = context
    def timeout(*args):
        raise TimeoutError('timeout')
    syn.restPOST = timeout
    output = tmp_path / 'result.json'
    with pytest.raises(TimeoutError):
        execute_dataset_rebuild(syn, plan, output, Dataset, Ref, dict)
    report = json.loads(output.read_text())
    assert report['status'] == 'failed'
    assert 'outcome may be unknown' in report['phase']
    assert report['dataset_id'] is None


def test_competing_dataset_executions_reserve_report_before_remote_write(context, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    syn, plan = context
    entered, release = Event(), Event()
    output = tmp_path / 'result.json'

    def blocked_post(path, body):
        entered.set()
        assert release.wait(5)
        raise TimeoutError('outcome unknown')

    syn.restPOST = blocked_post
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(execute_dataset_rebuild, syn, plan, output, Dataset, Ref, dict)
        try:
            assert entered.wait(5)
            second = pool.submit(execute_dataset_rebuild, syn, plan, output, Dataset, Ref, dict)
            with pytest.raises(FileExistsError):
                second.result(timeout=5)
        finally:
            release.set()
        with pytest.raises(TimeoutError):
            first.result(timeout=5)
    report = json.loads(output.read_text())
    assert report['status'] == 'failed'
    assert 'outcome may be unknown' in report['phase']
