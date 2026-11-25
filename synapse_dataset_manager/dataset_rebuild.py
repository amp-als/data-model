"""Metadata-only Dataset rebuild planning helpers."""
from __future__ import annotations

from collections import defaultdict


def rebuild_versions(syn, entity_id):
    """Read every entity version using the paginated metadata endpoint."""
    versions, offset = [], 0
    while True:
        page = syn.restGET(f"/entity/{entity_id}/version?limit=100&offset={offset}")['results']
        versions.extend(page)
        if len(page) < 100:
            return versions
        offset += len(page)


def index_file_rebuild_report(report):
    """Index completed File rebuilds, retaining duplicate candidates."""
    index = defaultdict(list)
    for target in report.get('created', []):
        old_id, new_id = target.get('originalEntityId'), target.get('entityId')
        for version in target.get('versions', []):
            if old_id and new_id and version.get('label'):
                index[(old_id, version['label'])].append({
                    'id': new_id, 'version': version['versionNumber'],
                    'label': version['label'],
                    'sourceModifiedOn': version.get('sourceModifiedOn'),
                })
    return index


def choose_candidate(member, candidates, interactive=True, input_fn=input, require_review=False):
    """Resolve candidates explicitly; keeping the original is an explicit choice."""
    if len(candidates) == 1 and not require_review:
        return candidates[0]
    if not interactive:
        raise ValueError(f"Ambiguous or missing replacement for {member}: {len(candidates)} candidates")
    print(f'Choose a replacement for {member}:')
    for index, candidate in enumerate(candidates, 1):
        print(f'  {index}: {candidate}')
    print('  k: keep original pinned member; q: abort')
    while True:
        answer = input_fn('Selection: ').strip().lower()
        if answer == 'k':
            return None
        if answer == 'q':
            raise ValueError('Manifest generation aborted')
        if answer.isdigit() and 1 <= int(answer) <= len(candidates):
            return candidates[int(answer) - 1]


def build_folder_rebuild_draft(source_snapshots, replacement_files,
                               interactive=True, input_fn=input, file_rebuild_report=None):
    """Match reviewed report and exact filename/label candidates without guessing."""
    by_name = defaultdict(list)
    for entity in replacement_files:
        by_name[entity['name']].append(entity)
    report_index = {}
    if file_rebuild_report is not None:
        if file_rebuild_report.get('status') != 'completed':
            raise ValueError('File rebuild report is incomplete')
        report_index = index_file_rebuild_report(file_rebuild_report)
        if not report_index:
            raise ValueError('File rebuild report contains no completed original-to-new mappings')
    releases = []
    for snapshot in source_snapshots:
        release = {'source_dataset_version': snapshot['versionNumber'],
                   'label': snapshot['versionLabel'],
                   'comment': snapshot.get('versionComment', ''),
                   'member_replacements': {}}
        for member in snapshot['members']:
            files = by_name.get(member['name'], [])
            candidates = list(report_index.get((member['id'], member.get('versionLabel')), []))
            for entity in files:
                for version in entity['versions']:
                    if version.get('versionLabel') == member.get('versionLabel') and member.get('versionLabel'):
                        candidates.append({'id': entity['id'], 'version': version['versionNumber'],
                                           'label': version['versionLabel'],
                                           'modifiedOn': version.get('modifiedOn'),
                                           'comment': version.get('versionComment'),
                                           'contentMd5': version.get('contentMd5'),
                                           'contentSize': version.get('contentSize')})
            candidates = list({(item['id'], item['version']): item for item in candidates}.values())
            chosen = choose_candidate(member, candidates, interactive, input_fn, require_review=True)
            if chosen:
                release['member_replacements'][member['id']] = chosen
            else:
                release.setdefault('kept_members', []).append({
                    'id': member['id'], 'version': member['version'],
                    'reason': 'explicit interactive keep'})
        releases.append(release)
    return {'releases': releases}


def build_dataset_rebuild_draft(source_snapshots, file_rebuild_report,
                                interactive=True, input_fn=input):
    """Build release substitutions from a completed File rebuild report.

    A report identifies the old IDs requiring replacement. For those IDs, absent
    labels and duplicate matches are resolved explicitly, never silently kept.
    """
    if file_rebuild_report.get('status') != 'completed':
        raise ValueError('File rebuild report is incomplete; inspect partial results before retrying')
    replacements = index_file_rebuild_report(file_rebuild_report)
    old_ids = {target.get('originalEntityId') for target in file_rebuild_report.get('created', [])}
    old_ids.discard(None)
    if not old_ids:
        raise ValueError('File rebuild report contains no completed original-to-new mappings')
    releases = []
    for snapshot in source_snapshots:
        release = {'source_dataset_version': snapshot['versionNumber'],
                   'label': snapshot['versionLabel'],
                   'comment': snapshot.get('versionComment', ''),
                   'member_replacements': {}}
        for member in snapshot['members']:
            if member['id'] not in old_ids:
                continue
            candidates = replacements.get((member['id'], member.get('versionLabel')), [])
            chosen = choose_candidate(member, candidates, interactive, input_fn, require_review=True)
            if chosen:
                release['member_replacements'][member['id']] = chosen
            else:
                release.setdefault('kept_members', []).append({
                    'id': member['id'], 'version': member['version'],
                    'reason': 'explicit interactive keep'})
        releases.append(release)
    return {'releases': releases}


def dataset_schema(columns):
    """Return ordered, complete user-visible column definitions for comparison."""
    from dataclasses import fields, is_dataclass
    from enum import Enum

    def plain(value):
        if isinstance(value, Enum):
            return value.value
        if is_dataclass(value):
            return {field.name: plain(getattr(value, field.name)) for field in fields(value)
                    if field.name not in ('id', '_last_persistent_instance')}
        if isinstance(value, (list, tuple)):
            return [plain(item) for item in value]
        if isinstance(value, dict):
            return {key: plain(item) for key, item in value.items()}
        return value

    values = columns.values() if isinstance(columns, dict) else (columns or [])
    return [plain(column) for column in values]


def execute_dataset_rebuild(syn, plan, output, dataset_class, entity_ref_class, wiki_class):
    """Reconstruct snapshots, stopping on any uncertain or mismatched result."""
    import copy
    import json
    import re
    from synapse_dataset_manager.rebuild_reporting import reserve_rebuild_report, save_rebuild_report

    report = {'status': 'preflight', 'source_dataset_id': plan['source_dataset_id'],
              'output_name': plan['output_name'], 'dataset_id': None,
              'releases': [], 'wiki': {'status': 'not copied', 'pages': []},
              'phase': 'preflight'}

    reserve_rebuild_report(output, report)

    def save():
        save_rebuild_report(output, report)

    try:
        # Resolve and validate the entire latest tree before creating anything. The
        # SDK downloads markdown here; this function is called only with --execute.
        pending = {str(header['id']): header for header in plan['wiki_pages']}
        if len(pending) != len(plan['wiki_pages']):
            raise ValueError('Duplicate wiki page IDs')
        ordered_wiki = []
        seen = set()
        while pending:
            ready = [key for key, header in pending.items()
                     if not header.get('parentId') or str(header['parentId']) in seen]
            if not ready:
                raise ValueError('Wiki hierarchy contains a missing parent or cycle')
            for key in ready:
                header = pending.pop(key)
                page = syn.getWiki(plan['source_dataset_id'], subpageId=key)
                handles = syn.getWikiAttachments(page)
                attachment_ids = sorted({str(value) for value in page.get('attachmentFileHandleIds', [])} |
                                        {str(handle['id']) for handle in handles if handle.get('id')})
                attachments = [{'id': str(handle.get('id', '')), 'name': handle.get('fileName')}
                               for handle in handles]
                if attachment_ids or attachments:
                    print(f"WARNING: source wiki page {key} has attachments {attachment_ids}; "
                          "they will NOT be copied. Reattach them manually on the replacement Dataset.")
                markdown = page.get('markdown')
                if not isinstance(markdown, str):
                    raise ValueError(f'Wiki page {key} has no readable markdown')
                parent = str(header['parentId']) if header.get('parentId') else None
                if (str(page.get('parentWikiId')) if page.get('parentWikiId') else None) != parent:
                    raise ValueError(f'Wiki page {key} hierarchy changed since preview')
                ordered_wiki.append({'id': key, 'parent': parent,
                                     'title': page.get('title'), 'markdown': markdown,
                                     'attachment_ids': attachment_ids, 'attachments': attachments,
                                     'synapse_links': sorted(set(re.findall(r'\bsyn\d+\b', markdown, re.I)))})
                seen.add(key)
        if sum(page['parent'] is None for page in ordered_wiki) > 1:
            raise ValueError('Wiki hierarchy has multiple root pages')
        source = dataset_class(id=plan['source_dataset_id']).get(synapse_client=syn)
        if dataset_schema(source.columns) != plan['schema']:
            raise ValueError('Source schema changed since preflight')
        columns = copy.deepcopy(list(source.columns.values()) if isinstance(source.columns, dict)
                                else source.columns or [])
        report['phase'] = 'creating dataset (outcome may be unknown on timeout)'
        save()
        # POST is create-only. Dataset.store() resolves existing names and can update
        # an existing entity, including the source, rather than creating a new one.
        entity = syn.restPOST('/entity', json.dumps({
            'name': plan['output_name'], 'parentId': plan['output_parent_id'],
            'concreteType': 'org.sagebionetworks.repo.model.table.Dataset',
            'description': plan.get('description'),
            'columnIds': [], 'items': []}))
        new_id = entity['id']
        if not new_id or new_id == plan['source_dataset_id']:
            raise ValueError('Create returned an invalid or source Dataset ID')
        report['dataset_id'] = new_id
        report['phase'] = 'copying schema'
        save()
        dataset = dataset_class(id=new_id).get(synapse_client=syn)
        dataset.include_default_columns = False
        dataset.columns = {column.name: column for column in columns}
        dataset.store(synapse_client=syn)
        actual = dataset_class(id=new_id).get(synapse_client=syn)
        if dataset_schema(actual.columns) != plan['schema']:
            raise ValueError('Copied schema differs from source schema')
        page_ids = {}
        for page in ordered_wiki:
            entry = {'source_id': page['id'], 'new_id': None, 'parent_source_id': page['parent'],
                     'synapse_links': page['synapse_links'], 'status': 'pending',
                     'uncopied_attachment_ids': page['attachment_ids'],
                     'uncopied_attachments': page['attachments']}
            report['wiki']['pages'].append(entry)
            report['phase'] = 'creating wiki page (outcome may be unknown on timeout)'
            save()
            new_page = syn.store(wiki_class(owner=new_id, title=page['title'],
                                            markdown=page['markdown'],
                                            parentWikiId=page_ids.get(page['parent'])))
            new_page_id = str(new_page['id'])
            entry['new_id'] = new_page_id
            page_ids[page['id']] = new_page_id
            report['phase'] = 'verifying wiki page'
            save()
            actual_page = syn.getWiki(new_id, subpageId=new_page_id)
            actual_parent = str(actual_page.get('parentWikiId')) if actual_page.get('parentWikiId') else None
            if (actual_page.get('title') != page['title'] or
                    actual_page.get('markdown') != page['markdown'] or
                    actual_parent != page_ids.get(page['parent']) or
                    actual_page.get('attachmentFileHandleIds') or syn.getWikiAttachments(actual_page)):
                raise ValueError(f'Wiki page {new_page_id} verification failed')
            entry['status'] = 'verified'
            save()
        report['wiki']['status'] = ('verified; attachments require manual copying'
                                    if any(page['attachment_ids'] or page['attachments'] for page in ordered_wiki)
                                    else 'verified' if ordered_wiki else 'source has no wiki')
        save()
        for release in plan['releases']:
            entry = {'source_dataset_version': release['source_dataset_version'],
                     'label': release['label'], 'status': 'pending', 'version': None}
            report['releases'].append(entry)
            report['phase'] = 'storing release (outcome may be unknown on timeout)'
            entry['expected_members'] = release['members']
            save()
            dataset = dataset_class(id=new_id).get(synapse_client=syn)
            dataset.include_default_columns = False
            dataset.items = [entity_ref_class(id=member_id, version=version)
                             for member_id, version in release['members'].items()]
            dataset.annotations = copy.deepcopy(release['annotations'])
            dataset.store(synapse_client=syn)
            report['phase'] = 'creating snapshot (outcome may be unknown on timeout)'
            save()
            transaction = dataset.snapshot(label=release['label'], comment=release['comment'],
                                           synapse_client=syn)
            version = transaction.snapshot_version_number
            if not isinstance(version, int) or isinstance(version, bool) or version < 1:
                raise ValueError('Snapshot transaction did not return a valid version')
            entry['version'] = version
            report['phase'] = 'verifying snapshot'
            save()
            actual = dataset_class(id=new_id, version_number=version).get(synapse_client=syn)
            actual_members = {item.id: item.version for item in actual.items}
            actual_annotations = dict(syn.get_annotations(new_id, version=version))
            checks = {'members': len(actual_members) == len(actual.items) and actual_members == release['members'],
                      'annotations': actual_annotations == release['annotations'],
                      'label': actual.version_label == release['label'],
                      'comment': actual.version_comment == release['comment'],
                      'schema': dataset_schema(actual.columns) == plan['schema']}
            entry['checks'] = checks
            if not all(checks.values()):
                raise ValueError(f'Snapshot {version} verification failed: {checks}')
            entry['status'] = 'verified'
            save()
        report.update(status='completed', phase='complete')
        save()
        return report
    except Exception as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        save()
        raise


def audit_dataset_rebuild(syn, plan, report, dataset_class, wiki_markdown=False):
    """Independently compare a completed execution to a freshly validated plan."""
    if (report.get('status') != 'completed' or
            report.get('source_dataset_id') != plan['source_dataset_id'] or
            report.get('output_name') != plan['output_name'] or
            not report.get('dataset_id') or report['dataset_id'] == plan['source_dataset_id']):
        raise ValueError('Execution report does not identify a completed matching rebuild')
    entries = report.get('releases', [])
    by_source = {entry['source_dataset_version']: entry for entry in entries}
    if (len(by_source) != len(entries) or len(entries) != len(plan['releases']) or
            set(by_source) != {r['source_dataset_version'] for r in plan['releases']}):
        raise ValueError('Execution report release mapping does not match manifest')
    versions = [entry.get('version') for entry in entries]
    if any(not isinstance(v, int) or isinstance(v, bool) or v < 1 for v in versions) or len(set(versions)) != len(versions):
        raise ValueError('Execution report contains invalid or duplicate replacement versions')
    new_id = report['dataset_id']
    entity = syn.get(new_id, downloadFile=False)
    identity = {'id': entity.get('id') == new_id,
                'type': entity.get('concreteType') == 'org.sagebionetworks.repo.model.table.Dataset',
                'name': entity.get('name') == plan['output_name'],
                'parent': entity.get('parentId') == plan['output_parent_id']}
    actual_versions = [item['versionNumber'] for item in rebuild_versions(syn, new_id)]
    valid_versions = all(isinstance(v, int) and not isinstance(v, bool) and v > 0
                         for v in actual_versions)
    versions_match = (valid_versions and len(actual_versions) == len(set(actual_versions))
                      and set(actual_versions) == set(versions))
    results = []
    for release in plan['releases']:
        entry = by_source[release['source_dataset_version']]
        actual = dataset_class(id=new_id, version_number=entry['version']).get(synapse_client=syn)
        members = {item.id: item.version for item in actual.items}
        checks = {'members': len(members) == len(actual.items) and members == release['members'],
                  'annotations': dict(syn.get_annotations(new_id, version=entry['version'])) == release['annotations'],
                  'label': actual.version_label == release['label'],
                  'comment': actual.version_comment == release['comment'],
                  'schema': dataset_schema(actual.columns) == plan['schema']}
        results.append({'source_dataset_version': release['source_dataset_version'],
                        'version': entry['version'], 'checks': checks})
    pages = report.get('wiki', {}).get('pages', [])
    source_headers = {str(h['id']): h for h in plan['wiki_pages']}
    target_list = list(syn.getWikiHeaders(new_id))
    target_headers = {str(h['id']): h for h in target_list}
    mapping = {str(p['source_id']): str(p['new_id']) for p in pages if p.get('new_id')}
    structure = (len(mapping) == len(pages) == len(source_headers) == len(target_headers) == len(target_list)
                 and set(mapping) == set(source_headers) and set(mapping.values()) == set(target_headers))
    if structure:
        for old, new in mapping.items():
            source, target = source_headers[old], target_headers[new]
            parent = str(source['parentId']) if source.get('parentId') else None
            target_parent = str(target['parentId']) if target.get('parentId') else None
            if source.get('title') != target.get('title') or target_parent != mapping.get(parent):
                structure = False
    markdown = None
    if wiki_markdown and structure:
        markdown = True
        for old, new in mapping.items():
            source_text = syn.getWiki(plan['source_dataset_id'], subpageId=old).get('markdown')
            target_text = syn.getWiki(new_id, subpageId=new).get('markdown')
            if not isinstance(source_text, str) or not isinstance(target_text, str) or source_text != target_text:
                markdown = False
    return {'dataset_id': new_id, 'identity': {'checks': identity,
            'actual': {'id': entity.get('id'), 'type': entity.get('concreteType'),
                       'name': entity.get('name'), 'parent': entity.get('parentId')},
            'expected': {'id': new_id, 'name': plan['output_name'], 'parent': plan['output_parent_id']}},
            'versions': {'match': versions_match, 'actual': actual_versions, 'expected': versions},
            'releases': results,
            'wiki': {'headers_match': structure, 'markdown_match': markdown,
                     'exception': 'Attachments are not copied; reattach manually. Markdown is unchecked unless opted in.'},
            'passed': (all(identity.values()) and versions_match and
                       all(all(r['checks'].values()) for r in results) and structure and markdown is not False)}
