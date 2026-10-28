"""Reviewable update plans and strict stale-state validation (no mutations)."""

import hashlib
import json
from pathlib import Path

FORMAT_VERSION = 1


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False).encode()).hexdigest()


def file_digest(path):
    sha = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(block)
    return sha.hexdigest()


def validate_annotations(annotations):
    if not isinstance(annotations, dict) or not annotations:
        raise ValueError('Update annotations must be a nonempty object')
    for target, entry in annotations.items():
        if not isinstance(target, str) or not isinstance(entry, dict) or len(entry) != 1:
            raise ValueError('Each target must have exactly one filename entry')
        name, values = next(iter(entry.items()))
        if (not isinstance(name, str) or not name or name in ('.', '..')
                or '/' in name or '\\' in name or not isinstance(values, dict)):
            raise ValueError(f'Invalid annotation entry for {target}')
        if values.get('_staging_id') is not None and not isinstance(values['_staging_id'], str):
            raise ValueError(f'Invalid _staging_id for {target}')


def build_plan(backend, dataset_id, workflow, annotations, options):
    """Compile legacy annotation artifacts into explicit, fingerprinted actions."""
    validate_annotations(annotations)
    dataset_state = backend.snapshot(dataset_id)
    members = backend.members(dataset_id)
    member_ids = {item['id'] for item in members}
    options = dict(options)
    local_dir = options.get('local_files_dir')
    local_files = {}
    if local_dir:
        local_dir = str(Path(local_dir).resolve(strict=True))
        options['local_files_dir'] = local_dir
        for path in Path(local_dir).iterdir():
            if path.is_file():
                key = path.name.lower()
                if key in local_files:
                    raise ValueError(f'Ambiguous local filename: {path.name}')
                local_files[key] = str(path.resolve())
    actions, snapshots, sources = [], {dataset_id: dataset_state}, set()
    release = options.get('release_folder')
    if release:
        snapshots[release] = backend.snapshot(release)
        if snapshots[release].get('concreteType') not in (
            'org.sagebionetworks.repo.model.Folder', 'org.sagebionetworks.repo.model.Project',
        ):
            raise ValueError('Release destination must be a folder or project')
    for target, entry in sorted(annotations.items()):
        name, values = next(iter(entry.items()))
        source = values.get('_staging_id') or None
        state = backend.snapshot(target)
        snapshots[target] = state
        if state.get('concreteType') != 'org.sagebionetworks.repo.model.FileEntity':
            raise ValueError(f'Update target {target} is not a file entity')
        if target in member_ids:
            if name != state['name']:
                raise ValueError(f'Implicit rename of existing file {target} is not allowed')
            if source and source != target and local_dir:
                raise ValueError('Cannot combine staging uploads with --local-files-dir')
            kind = 'version_staging' if source and source != target else ('version_local' if local_dir else 'annotate')
        else:
            kind = 'add'
            if not release:
                raise ValueError('New files require --release-folder before planning')
            if source and source != target:
                raise ValueError(f'New file {target} must use its own staging ID')
        action = {'kind': kind, 'target_id': target, 'filename': name,
                  'source_id': source if kind == 'version_staging' else None,
                  'destination': release if kind == 'add' else state['parentId'],
                  'refresh_membership': kind != 'annotate' or bool(options.get('version_label'))}
        if kind == 'version_staging':
            if source in sources or source in annotations:
                raise ValueError(f'Staging source {source} is reused or also an update target')
            sources.add(source)
            snapshots[source] = backend.snapshot(source)
            if (snapshots[source].get('concreteType') != 'org.sagebionetworks.repo.model.FileEntity'
                    or not snapshots[source].get('dataFileHandleId')):
                raise ValueError(f'Staging source {source} is not a downloadable file entity')
            if not snapshots[source].get('versionNumber'):
                raise ValueError(f'Staging source {source} has no pinnable version')
        if kind == 'version_local':
            path = local_files.get(name.lower())
            if not path:
                raise ValueError(f'No local file for {name}')
            action['local_path'] = path
            action['sha256'] = file_digest(path)
        actions.append(action)
    additions = [(a['destination'], a['filename']) for a in actions if a['kind'] == 'add']
    if len(additions) != len(set(additions)):
        raise ValueError('Duplicate addition filenames')
    if additions:
        occupants = backend.children(release)
        for action in actions:
            if action['kind'] == 'add' and any(
                item['name'] == action['filename'] and item['id'] != action['target_id']
                for item in occupants
            ):
                raise ValueError(f'Release filename already exists: {action["filename"]}')
    # Detect a dataset changed while the plan was being collected.
    if backend.snapshot(dataset_id) != dataset_state or backend.members(dataset_id) != members:
        raise ValueError('Dataset changed during planning; retry preparation')
    payload = {'format_version': FORMAT_VERSION, 'dataset_id': dataset_id,
               'workflow': workflow, 'annotations_sha256': digest(annotations),
               'options': options, 'members': members, 'snapshots': snapshots,
               'actions': actions}
    return {**payload, 'plan_id': digest(payload)}


def load_plan(path):
    with open(path) as stream:
        plan = json.load(stream)
    if not isinstance(plan, dict) or plan.get('format_version') != FORMAT_VERSION:
        raise ValueError('Unsupported update plan format')
    payload = {key: value for key, value in plan.items() if key != 'plan_id'}
    if plan.get('plan_id') != digest(payload):
        raise ValueError('Update plan was edited or corrupted; generate a new plan')
    return plan


def write_plan(path, plan):
    # Never overwrite an artifact that may already have been reviewed.
    with open(path, 'x') as stream:
        json.dump(plan, stream, indent=2, sort_keys=True)
        stream.write('\n')


def assert_current(reviewed, current):
    if reviewed != current:
        changed = [key for key in current if key != 'plan_id' and reviewed.get(key) != current[key]]
        raise ValueError(f'Stale or mismatched update plan ({", ".join(changed)}); generate and review a new plan')
