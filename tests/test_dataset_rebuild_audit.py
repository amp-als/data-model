from copy import deepcopy

import pytest

from synapse_dataset_manager.dataset_rebuild import (audit_dataset_rebuild, build_folder_rebuild_draft,
                                                     build_dataset_rebuild_draft)
from test_dataset_rebuild_execution import Dataset, Ref, context  # shared in-memory SDK fixture



def configure_target(syn, versions):
    syn.get = lambda entity_id, downloadFile: {
        'id': entity_id, 'name': 'new', 'parentId': 'synProject',
        'concreteType': 'org.sagebionetworks.repo.model.table.Dataset'} if downloadFile is False else pytest.fail('download')
    syn.restGET = lambda path: {'results': [{'versionNumber': version} for version in versions]}


def test_audit_checks_snapshots_without_markdown(context):
    syn, plan = context
    configure_target(syn, [7, 8])
    Dataset.snapshots = {('synNew', 7): {'items': [Ref('synFile', 1)],
                         'columns': deepcopy(Dataset.states['synSource']['columns']),
                         'version_label': 'v1', 'version_comment': 'one',
                         'annotations': {'first': ['one']}},
                         ('synNew', 8): {'items': [Ref('synOther', 3)],
                         'columns': deepcopy(Dataset.states['synSource']['columns']),
                         'version_label': 'v2', 'version_comment': 'two',
                         'annotations': {'second': ['two']}}}
    syn.getWikiHeaders = lambda owner: []
    syn.getWiki = lambda *a, **kw: pytest.fail('markdown download not opted in')
    report = {'status': 'completed', 'source_dataset_id': 'synSource', 'output_name': 'new',
              'dataset_id': 'synNew', 'wiki': {'pages': []}, 'releases': [
                  {'source_dataset_version': 1, 'version': 7},
                  {'source_dataset_version': 2, 'version': 8}]}
    assert audit_dataset_rebuild(syn, plan, report, Dataset)['passed']
    configure_target(syn, [7, 8, 9])
    extra = audit_dataset_rebuild(syn, plan, report, Dataset)
    assert not extra['passed'] and extra['versions']['actual'] == [7, 8, 9]
    configure_target(syn, [7, 8])
    Dataset.snapshots[('synNew', 8)]['version_comment'] = 'wrong'
    result = audit_dataset_rebuild(syn, plan, report, Dataset)
    assert not result['passed'] and not result['releases'][1]['checks']['comment']
    report['releases'][1]['version'] = 7
    with pytest.raises(ValueError, match='duplicate'):
        audit_dataset_rebuild(syn, plan, report, Dataset)


def test_combined_candidates_deduplicate_and_require_review():
    snapshots = [{'versionNumber': 1, 'versionLabel': 'v1', 'members': [
        {'id': 'synOld', 'version': 1, 'name': 'a', 'versionLabel': 'v1'}]}]
    report = {'status': 'completed', 'created': [{'originalEntityId': 'synOld', 'entityId': 'synNew',
              'versions': [{'label': 'v1', 'versionNumber': 2}]}]}
    files = [{'id': 'synNew', 'name': 'a', 'versions': [{'versionLabel': 'v1', 'versionNumber': 2}]}]
    with pytest.raises(ValueError):
        build_folder_rebuild_draft(snapshots, files, False, file_rebuild_report=report)
    draft = build_folder_rebuild_draft(snapshots, files, input_fn=lambda _: '1', file_rebuild_report=report)
    assert draft['releases'][0]['member_replacements']['synOld']['id'] == 'synNew'


def test_audit_wiki_headers_and_opt_in_markdown(context):
    syn, plan = context
    configure_target(syn, [])
    plan['releases'] = []
    plan['wiki_pages'] = [{'id': '1', 'title': 'Root'}]
    report = {'status': 'completed', 'source_dataset_id': 'synSource', 'output_name': 'new',
              'dataset_id': 'synNew', 'releases': [],
              'wiki': {'pages': [{'source_id': '1', 'new_id': '10'}]}}
    syn.getWikiHeaders = lambda owner: [{'id': '10', 'title': 'Root'}]
    calls = []
    def get_wiki(owner, subpageId):
        calls.append(owner)
        return {'markdown': 'source' if owner == 'synSource' else 'different'}
    syn.getWiki = get_wiki
    result = audit_dataset_rebuild(syn, plan, report, Dataset)
    assert result['passed'] and result['wiki']['markdown_match'] is None and not calls
    result = audit_dataset_rebuild(syn, plan, report, Dataset, wiki_markdown=True)
    assert not result['passed'] and calls == ['synSource', 'synNew']
    syn.getWiki = lambda owner, subpageId: {'markdown': 'same'}
    assert audit_dataset_rebuild(syn, plan, report, Dataset, wiki_markdown=True)['passed']
    syn.getWikiHeaders = lambda owner: [{'id': '10', 'title': 'Changed'}]
    assert not audit_dataset_rebuild(syn, plan, report, Dataset)['passed']


@pytest.mark.parametrize('field,value', [('name', 'renamed'), ('parentId', 'synElsewhere'),
                                        ('id', 'synOther'), ('concreteType', 'wrong')])
def test_audit_detects_target_identity_mismatch(context, field, value):
    syn, plan = context
    configure_target(syn, [])
    plan['releases'] = []
    metadata = syn.get('synNew', downloadFile=False)
    metadata[field] = value
    syn.get = lambda entity_id, downloadFile: metadata
    syn.getWikiHeaders = lambda owner: []
    report = {'status': 'completed', 'source_dataset_id': 'synSource', 'output_name': 'new',
              'dataset_id': 'synNew', 'releases': [], 'wiki': {'pages': []}}
    result = audit_dataset_rebuild(syn, plan, report, Dataset)
    assert not result['passed']
    check = {'parentId': 'parent', 'concreteType': 'type'}.get(field, field)
    assert result['identity']['checks'][check] is False
    assert result['identity']['actual'][check] == value


def test_audit_detects_unexpected_target_snapshot(context):
    syn, plan = context
    configure_target(syn, [1])
    plan['releases'] = []
    syn.getWikiHeaders = lambda owner: []
    report = {'status': 'completed', 'source_dataset_id': 'synSource', 'output_name': 'new',
              'dataset_id': 'synNew', 'releases': [], 'wiki': {'pages': []}}
    result = audit_dataset_rebuild(syn, plan, report, Dataset)
    assert not result['passed']
    assert result['versions'] == {'match': False, 'actual': [1], 'expected': []}


@pytest.mark.parametrize('pages', [({}, {}), ({'markdown': None}, {'markdown': None}),
                                   ({'markdown': 'ok'}, {}), ({}, {'markdown': 'ok'})])
def test_audit_rejects_unreadable_markdown(context, pages):
    syn, plan = context
    configure_target(syn, [])
    plan['releases'] = []
    plan['wiki_pages'] = [{'id': '1', 'title': 'Root'}]
    syn.getWikiHeaders = lambda owner: [{'id': '10', 'title': 'Root'}]
    syn.getWiki = lambda owner, subpageId: pages[0] if owner == 'synSource' else pages[1]
    report = {'status': 'completed', 'source_dataset_id': 'synSource', 'output_name': 'new',
              'dataset_id': 'synNew', 'releases': [],
              'wiki': {'pages': [{'source_id': '1', 'new_id': '10'}]}}
    result = audit_dataset_rebuild(syn, plan, report, Dataset, wiki_markdown=True)
    assert not result['passed'] and result['wiki']['markdown_match'] is False


def test_report_only_requires_explicit_completed_status():
    with pytest.raises(ValueError, match='incomplete'):
        build_dataset_rebuild_draft([], {'created': [{'originalEntityId': 'syn1',
                                                     'entityId': 'syn2', 'versions': []}]})
