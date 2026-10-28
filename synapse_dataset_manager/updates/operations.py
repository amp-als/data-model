"""Shared Synapse execution adapter for plan-driven updates.

The engine owns review/preflight/reporting; this module owns remote operations.
The CLI injects only annotation cleaning, not execution policy.
"""

import json
from pathlib import Path
import shutil

from synapseclient.models import Dataset, EntityRef, File

from .plans import digest, file_digest


class SynapseOperations:
    def __init__(self, syn, clean_annotations):
        self.syn = syn
        self.clean_annotations = clean_annotations

    def snapshot(self, entity_id):
        entity = self.syn.get(entity_id, downloadFile=False)
        state = {key: entity.get(key) for key in (
            'id', 'etag', 'name', 'parentId', 'versionNumber', 'versionLabel',
            'dataFileHandleId', 'concreteType',
        )}
        if not state['etag'] or not state['id']:
            raise ValueError(f'Cannot fingerprint entity {entity_id}: missing ID/etag')
        annotations = self.syn.get_annotations(entity_id)
        # Datetime annotation values have a stable ISO-like string representation.
        state['annotations_sha256'] = digest(json.loads(json.dumps(dict(annotations), default=str)))
        return state

    def members(self, dataset_id):
        dataset = Dataset(id=dataset_id).get(synapse_client=self.syn)
        return sorted(({'id': item.id, 'version': item.version} for item in dataset.items),
                      key=lambda item: (item['id'], str(item['version'])))

    def children(self, folder_id):
        return sorted(({'id': child['id'], 'name': child['name']}
                       for child in self.syn.getChildren(folder_id)), key=lambda item: item['id'])

    def prepare_content(self, plan, directory):
        """Stage all bytes before writes; pin remote downloads to reviewed versions."""
        paths = {}
        for index, action in enumerate(plan['actions']):
            target = action['target_id']
            destination = Path(directory) / str(index)
            if action['kind'] == 'version_local':
                shutil.copyfile(action['local_path'], destination)
                if file_digest(destination) != action['sha256']:
                    raise ValueError(f'Local content changed while staging {target}')
                paths[target] = str(destination)
            elif action['kind'] == 'version_staging':
                source = action['source_id']
                state = plan['snapshots'][source]
                download_dir = Path(directory) / f'download-{index}'
                download_dir.mkdir()
                entity = self.syn.get(source, version=state['versionNumber'],
                                      downloadLocation=str(download_dir), downloadFile=True)
                if entity.get('dataFileHandleId') != state['dataFileHandleId']:
                    raise ValueError(f'Staging file handle changed for {source}')
                shutil.copyfile(entity.path, destination)
                paths[target] = str(destination)
        return paths

    def apply(self, plan, action, annotations, paths):
        target = action['target_id']
        name = action['filename']
        cleaned = self.clean_annotations(annotations[target][name])
        options = plan['options']
        label = options.get('version_label')
        comment = options.get('version_comment')
        if action['kind'] in ('version_local', 'version_staging'):
            File(path=paths[target], id=target, name=name, annotations=cleaned,
                 version_label=label, version_comment=comment).store(synapse_client=self.syn)
        else:
            entity = self.syn.get(target, downloadFile=False)
            if action['kind'] == 'add':
                entity.name = name
                entity.parentId = action['destination']
            merged = dict(entity.annotations)
            merged.update(cleaned)
            entity.annotations = merged
            if comment:
                entity['versionComment'] = comment
            kwargs = {'forceVersion': bool(label)}
            if label:
                kwargs['versionLabel'] = label
            self.syn.store(entity, **kwargs)
        if action['refresh_membership']:
            # Pin the dataset reference to the newly stored version. Merely adding
            # a second EntityRef would leave the old version in the dataset too.
            entity = self.syn.get(target, downloadFile=False)
            dataset = Dataset(id=plan['dataset_id']).get(synapse_client=self.syn)
            dataset.items = [item for item in dataset.items if item.id != target]
            dataset.add_item(EntityRef(id=target, version=entity.versionNumber), synapse_client=self.syn)
            dataset.store(synapse_client=self.syn)

    def verify_dataset(self, plan, observed=None):
        expected = list(plan['members'])
        for action in plan['actions']:
            if action['refresh_membership']:
                target = action['target_id']
                state = observed[target] if observed is not None else self.snapshot(target)
                expected = [item for item in expected if item['id'] != target]
                expected.append({'id': target, 'version': state['versionNumber']})
        expected.sort(key=lambda item: (item['id'], str(item['version'])))
        return [] if self.members(plan['dataset_id']) == expected else ['dataset references differ from the planned result']

    def verify(self, plan, action, annotations):
        target = action['target_id']
        state = self.snapshot(target)
        failures = []
        if state['name'] != action['filename']:
            failures.append('filename differs')
        if state['parentId'] != action['destination']:
            failures.append('parent folder differs')
        label = plan['options'].get('version_label')
        if label and state['versionLabel'] != label:
            failures.append('version label differs')
        before = plan['snapshots'][target]
        if (action['kind'].startswith('version_') or label) and (
            not state['versionNumber'] or state['versionNumber'] <= (before['versionNumber'] or 0)
        ):
            failures.append('new version was not created')
        members = self.members(plan['dataset_id'])
        if not any(item['id'] == target and (
            not action['refresh_membership'] or item['version'] == state['versionNumber']
        ) for item in members):
            failures.append('dataset membership/version differs')
        actual = dict(self.syn.get_annotations(target))
        expected = self.clean_annotations(annotations[target][action['filename']])
        def values(value):
            return sorted(str(item) for item in (value if isinstance(value, list) else [value]))
        for field, value in expected.items():
            if field not in actual or values(actual[field]) != values(value):
                failures.append(f'annotation differs: {field}')
        return failures
