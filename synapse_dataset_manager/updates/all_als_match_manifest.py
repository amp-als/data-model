"""Reviewed, deterministic ALL ALS staging-to-Dataset match manifests."""

import json
from pathlib import Path

from .all_als_preflight import normalize


FORMAT_VERSION = 1


class MatchManifestReviewRequired(Exception):
    """Raised after a draft is written or when a draft has not been approved."""


def canonical_view(value, aliases):
    value = normalize(value)
    return aliases.get(value, value)


def resolve_aliases(raw_aliases, dictionary_views):
    """Validate exact raw-view aliases against the loaded dictionary."""
    aliases = {}
    for raw, target in (raw_aliases or {}).items():
        source_key, target_key = normalize(raw), normalize(target)
        if not source_key or not target_key:
            raise ValueError('ALL ALS view aliases cannot contain empty names')
        if source_key in aliases and aliases[source_key] != target_key:
            raise ValueError(f'Conflicting ALL ALS alias for {raw!r}')
        if target_key not in dictionary_views:
            raise ValueError(f'ALL ALS alias target is not a dictionary view: {target!r}')
        aliases[source_key] = target_key
    return aliases


def _view(annotation):
    value = annotation.get('viewName')
    if isinstance(value, list):
        value = value[0] if value else ''
    return value or ''


def _snapshot(syn, entity_id):
    entity = syn.get(entity_id, downloadFile=False)
    return {
        'id': entity_id,
        'name': entity.name,
        'etag': entity.get('etag'),
        'versionNumber': entity.get('versionNumber'),
    }


def _draft(dataset_id, existing, staging, names, groups, aliases, services, syn):
    sources = {
        source_id: {
            'source_synapse_id': source_id,
            'source_filename': next(iter(data)),
            'form_name': names.get(source_id, ''),
            'raw_view': groups.get(source_id, ''),
            'canonical_view': canonical_view(groups.get(source_id, ''), aliases),
        }
        for source_id, data in staging.items()
    }
    targets = {}
    for target_id, data in existing.items():
        filename, annotation = next(iter(data.items()))
        raw_view = _view(annotation)
        targets[target_id] = {
            'target_synapse_id': target_id,
            'target_filename': filename,
            'raw_view': raw_view,
            'canonical_view': canonical_view(raw_view, aliases),
        }

    mappings, ambiguous, unresolved = [], [], []
    for target_id, target in sorted(targets.items()):
        target_view = target['canonical_view']
        if target_view:
            candidates = [source for source in sources.values()
                          if source['canonical_view'] == target_view]
            if len(candidates) == 1:
                source = candidates[0]
                basis = 'canonical_view'
            elif len(candidates) > 1:
                exact = [source for source in candidates if services._norm_filename_for_match(
                    source['form_name']) == services._norm_filename_for_match(target['target_filename'])]
                if len(exact) == 1:
                    source, basis = exact[0], 'canonical_view_and_form_name'
                else:
                    ambiguous.append({**target, 'candidate_source_ids': [
                        source['source_synapse_id'] for source in candidates
                    ], 'reason': 'multiple staged files share canonical view'})
                    continue
            else:
                # Existing members absent from staging remain unchanged; this is
                # expected for partial releases, not an unresolved identity.
                continue
        else:
            exact = [source for source in sources.values() if services._norm_filename_for_match(
                source['form_name']) == services._norm_filename_for_match(target['target_filename'])]
            if len(exact) == 1:
                source, basis = exact[0], 'exact_form_name_without_view'
            elif len(exact) > 1:
                ambiguous.append({**target, 'candidate_source_ids': [
                    source['source_synapse_id'] for source in exact
                ], 'reason': 'multiple staged files share exact form name'})
                continue
            else:
                # Existing members absent from staging remain unchanged.
                continue
        mappings.append({**target, **source, 'match_basis': basis})

    # A source may not be proposed for two Dataset members. Do not greedily pick one.
    by_source = {}
    for mapping in mappings:
        by_source.setdefault(mapping['source_synapse_id'], []).append(mapping)
    conflicts = []
    duplicate_sources = {source for source, rows in by_source.items() if len(rows) > 1}
    if duplicate_sources:
        for source in sorted(duplicate_sources):
            rows = by_source[source]
            conflicts.append({'source_synapse_id': source,
                              'target_synapse_ids': [row['target_synapse_id'] for row in rows],
                              'reason': 'one staged file proposed for multiple Dataset members'})
        mappings = [row for row in mappings if row['source_synapse_id'] not in duplicate_sources]

    mapped_sources = {row['source_synapse_id'] for row in mappings}
    return {
        'format_version': FORMAT_VERSION,
        'status': 'draft',
        'dataset_id': dataset_id,
        'aliases': aliases,
        'mappings': mappings,
        'additions': [source for source in sources.values() if source['source_synapse_id'] not in mapped_sources],
        'unchanged_existing': [target for target in targets.values()
                               if target['target_synapse_id'] not in {row['target_synapse_id'] for row in mappings}],
        'unresolved': unresolved,
        'ambiguous': ambiguous,
        'conflicts': conflicts,
        'snapshots': {
            'dataset': _snapshot(syn, dataset_id),
            'targets': {target_id: _snapshot(syn, target_id) for target_id in targets},
            'sources': {source_id: _snapshot(syn, source_id) for source_id in sources},
        },
    }


def _assert_snapshot(syn, snapshot):
    current = _snapshot(syn, snapshot['id'])
    if current != snapshot:
        raise ValueError(f'Match manifest is stale: {snapshot["id"]} changed')


def _validate_approved(manifest, dataset_id, existing, staging, groups, aliases, syn):
    if manifest.get('format_version') != FORMAT_VERSION or manifest.get('dataset_id') != dataset_id:
        raise ValueError('Unsupported or wrong-dataset ALL ALS match manifest')
    if manifest.get('status') != 'approved':
        raise MatchManifestReviewRequired('Match manifest is a draft; review it and set status to "approved"')
    if any(manifest.get(key) for key in ('unresolved', 'ambiguous', 'conflicts')):
        raise ValueError('Approved ALL ALS match manifest still contains unresolved, ambiguous, or conflicting entries')
    snapshots = manifest.get('snapshots') or {}
    _assert_snapshot(syn, snapshots.get('dataset') or {})
    if set((snapshots.get('targets') or {})) != set(existing) or set((snapshots.get('sources') or {})) != set(staging):
        raise ValueError('Match manifest Dataset membership or staging source set changed')
    for snapshot in (snapshots.get('targets') or {}).values():
        _assert_snapshot(syn, snapshot)
    for snapshot in (snapshots.get('sources') or {}).values():
        _assert_snapshot(syn, snapshot)

    matches, target_ids, source_ids = {}, set(), set()
    for mapping in manifest.get('mappings') or []:
        target, source = mapping.get('target_synapse_id'), mapping.get('source_synapse_id')
        if target not in existing or source not in staging:
            raise ValueError('Match manifest references a non-current target or source')
        if target in target_ids or source in source_ids:
            raise ValueError('Match manifest has duplicate target or source assignment')
        target_ids.add(target)
        source_ids.add(source)
        target_annotation = next(iter(existing[target].values()))
        target_view = canonical_view(_view(target_annotation), aliases)
        source_view = canonical_view(groups.get(source, ''), aliases)
        if target_view and source_view != target_view:
            raise ValueError(f'Match manifest view mismatch: {target} ↔ {source}')
        matches[target] = source
    return matches


def resolve_manifest(path, dataset_id, existing, staging, names, groups, aliases, services, syn):
    """Write a draft on first pass; validate and return mappings after approval."""
    path = Path(path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        draft = _draft(dataset_id, existing, staging, names, groups, aliases, services, syn)
        with open(path, 'x') as stream:
            json.dump(draft, stream, indent=2, sort_keys=True)
            stream.write('\n')
        raise MatchManifestReviewRequired(
            f'ALL ALS preflight passed; review {path}, resolve entries, and set status to "approved" before rerunning'
        )
    with open(path) as stream:
        manifest = json.load(stream)
    return _validate_approved(manifest, dataset_id, existing, staging, groups, aliases, syn)
