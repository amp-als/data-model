"""Conservative, dataset-independent file identity and matching policies."""

import csv
from pathlib import Path


def prepare(syn, staging, directory, options, services):
    """Return names, local content paths, dictionary groups, and explicit targets.

    Content is only downloaded when a name column was explicitly requested.
    A manifest is CSV with canonical column names; omitted sources retain their
    original filenames. Identity sources are mutually exclusive.
    """
    names = {sid: next(iter(data)) for sid, data in staging.items()}
    paths, groups, targets = {}, {}, {}
    manifest = options.get('identity_manifest')
    column = options.get('name_column')
    if manifest and column:
        raise ValueError('Choose identity_manifest or name_column, not both')
    if manifest:
        seen = set()
        with open(manifest, newline='', encoding='utf-8-sig') as stream:
            reader = csv.DictReader(stream)
            if not {'source_synapse_id', 'source_filename'} & set(reader.fieldnames or []):
                raise ValueError('Identity manifest requires source_synapse_id or source_filename')
            for row in reader:
                sid = row.get('source_synapse_id', '').strip()
                filename = row.get('source_filename', '').strip()
                if not sid:
                    candidates = [key for key, data in staging.items() if next(iter(data)) == filename]
                    if len(candidates) != 1:
                        raise ValueError(f'Manifest source {filename!r} must resolve to exactly one staging file')
                    sid = candidates[0]
                if sid not in staging or (filename and filename != next(iter(staging[sid]))):
                    raise ValueError(f'Invalid manifest source: {sid}')
                if sid in seen:
                    raise ValueError(f'Duplicate manifest source: {sid}')
                seen.add(sid)
                names[sid] = row.get('release_filename', '').strip() or names[sid]
                if row.get('dictionary_group', '').strip():
                    groups[sid] = row['dictionary_group'].strip()
                if row.get('target_synapse_id', '').strip():
                    targets[sid] = row['target_synapse_id'].strip()
    if column:
        for sid, filename in names.items():
            path = services.download_file_for_analysis(syn, sid, directory)
            if not path:
                raise ValueError(f'Cannot read name column from {sid}')
            rows = services.load_metadata_file(path)
            if not rows or any(column not in row for row in rows):
                raise ValueError(f'Missing name column {column!r} in {filename}')
            values = {str(row[column]).strip() for row in rows if row[column] is not None and str(row[column]).strip()}
            if len(values) != 1:
                raise ValueError(f'{filename}: name column must have one distinct nonempty value')
            name = values.pop()
            suffix = Path(filename).suffix
            names[sid] = name if name.endswith(suffix) else name + suffix
            paths[sid] = path
    for sid, name in names.items():
        if not name or name in ('.', '..') or '/' in name or '\\' in name:
            raise ValueError(f'Invalid release filename for {sid}: {name!r}')
    return names, paths, groups, targets


def match(existing, staging, names, groups, targets, services):
    """Match explicit IDs, same IDs, then exact names; never silently choose ties."""
    by_name = {}
    for sid, data in existing.items():
        by_name.setdefault(next(iter(data)), []).append(sid)
    matches = {}
    for source, name in names.items():
        target = targets.get(source)
        if target and target not in existing:
            raise ValueError(f'Target {target} is not a member of the dataset')
        if source in existing:
            if target and target != source:
                raise ValueError(f'Source {source} is already a different dataset member')
            target = source
        if not target:
            candidates = by_name.get(name, [])
            if len(candidates) > 1:
                raise ValueError(f'Ambiguous existing filename: {name!r}')
            target = candidates[0] if candidates else None
        if target:
            if target in matches:
                raise ValueError(f'Multiple staging files target {target}')
            matches[target] = source
    additions = [names[sid] for sid in names if sid not in matches.values()]
    if len(additions) != len(set(additions)):
        raise ValueError('New staging files have duplicate release filenames')
    return matches
