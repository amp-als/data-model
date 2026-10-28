"""Mocked Synapse adapter tests; no network access."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from synapseclient import File as SynapseFile
from synapseclient.models import EntityRef

from synapse_dataset_manager.updates.operations import SynapseOperations
from synapse_dataset_manager.updates.plans import file_digest


class OperationTests(unittest.TestCase):
    def setUp(self):
        self.syn = Mock()
        self.ops = SynapseOperations(self.syn, lambda annotation: {
            key: value for key, value in annotation.items() if not key.startswith('_')
        })
        self.entity = SynapseFile(id='syn1', name='a.csv', parentId='synParent',
                                  etag='etag', versionNumber=2, versionLabel='v2',
                                  dataFileHandleId='handle')
        self.entity.annotations = {'species': ['human']}
        self.syn.get.return_value = self.entity
        self.syn.get_annotations.return_value = {'species': ['human']}
        self.action = {'kind': 'version_staging', 'target_id': 'syn1', 'filename': 'a.csv',
                       'source_id': 'synSource', 'destination': 'synParent', 'refresh_membership': True}
        self.plan = {'dataset_id': 'synDataset', 'options': {'version_label': 'v2', 'version_comment': 'release'},
                     'actions': [self.action], 'snapshots': {'syn1': {'versionNumber': 1}},
                     'members': [{'id': 'syn1', 'version': 1}]}
        self.annotations = {'syn1': {'a.csv': {'species': ['human'], '_staging_id': 'synSource'}}}

    def test_upload_uses_client_and_replaces_pinned_reference(self):
        with patch('synapse_dataset_manager.updates.operations.File') as file_model, \
             patch('synapse_dataset_manager.updates.operations.Dataset') as dataset_model:
            dataset = dataset_model.return_value.get.return_value
            dataset.items = [EntityRef(id='syn1', version=1), EntityRef(id='syn2', version=3)]
            self.ops.apply(self.plan, self.action, self.annotations, {'syn1': '/tmp/content'})
            file_model.return_value.store.assert_called_once_with(synapse_client=self.syn)
            self.assertEqual(dataset.items, [EntityRef(id='syn2', version=3)])
            dataset.add_item.assert_called_once_with(EntityRef(id='syn1', version=2), synapse_client=self.syn)
            dataset.store.assert_called_once_with(synapse_client=self.syn)
            self.assertNotIn('_staging_id', file_model.call_args.kwargs['annotations'])

    def test_prepare_download_is_version_pinned(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.csv'
            source.write_text('reviewed content')
            self.entity.path = str(source)
            self.plan['snapshots']['synSource'] = {'versionNumber': 7, 'dataFileHandleId': 'handle'}
            paths = self.ops.prepare_content(self.plan, directory)
            self.assertEqual(Path(paths['syn1']).read_text(), 'reviewed content')
            self.assertEqual(self.syn.get.call_args.kwargs['version'], 7)
            self.syn.store.assert_not_called()

    def test_changed_download_handle_rejected(self):
        self.plan['snapshots']['synSource'] = {'versionNumber': 7, 'dataFileHandleId': 'other-handle'}
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, 'handle changed'):
            self.ops.prepare_content(self.plan, directory)

    def test_local_content_is_copied_and_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.csv'
            source.write_text('reviewed content')
            self.action.update(kind='version_local', local_path=str(source), sha256=file_digest(source))
            paths = self.ops.prepare_content(self.plan, directory)
            source.write_text('changed later')
            self.assertEqual(Path(paths['syn1']).read_text(), 'reviewed content')
            with self.assertRaisesRegex(ValueError, 'Local content changed'):
                self.ops.prepare_content(self.plan, directory)

    def test_verification_uses_action_destination_and_annotation_values(self):
        self.plan['options']['release_folder'] = 'some-other-folder'
        with patch.object(self.ops, 'members', return_value=[{'id': 'syn1', 'version': 2}]):
            self.assertEqual(self.ops.verify(self.plan, self.action, self.annotations), [])
            self.syn.get_annotations.return_value = {'species': ['mouse']}
            self.assertIn('annotation differs: species', self.ops.verify(self.plan, self.action, self.annotations))

    def test_final_membership_rejects_unplanned_references(self):
        with patch.object(self.ops, 'members', return_value=[{'id': 'syn1', 'version': 2}]):
            self.assertEqual(self.ops.verify_dataset(self.plan), [])
        with patch.object(self.ops, 'members', return_value=[
            {'id': 'syn1', 'version': 2}, {'id': 'unplanned', 'version': 1},
        ]):
            self.assertTrue(self.ops.verify_dataset(self.plan))

    def test_add_moves_then_pins_the_resulting_version(self):
        self.action.update(kind='add', destination='synRelease')
        with patch('synapse_dataset_manager.updates.operations.Dataset') as dataset_model:
            dataset = dataset_model.return_value.get.return_value
            dataset.items = []
            self.ops.apply(self.plan, self.action, self.annotations, {})
            self.assertEqual(self.entity.parentId, 'synRelease')
            self.syn.store.assert_called_once_with(self.entity, forceVersion=True, versionLabel='v2')
            dataset.add_item.assert_called_once_with(EntityRef(id='syn1', version=2), synapse_client=self.syn)

    def test_missing_etag_fails_closed(self):
        self.entity.pop('etag')
        with self.assertRaisesRegex(ValueError, 'missing ID/etag'):
            self.ops.snapshot('syn1')

    def test_annotation_only_preserves_parent_and_unmentioned_annotations(self):
        self.action.update(kind='annotate', refresh_membership=False)
        self.plan['options']['version_label'] = None
        self.annotations['syn1']['a.csv'] = {'disease': 'ALS'}
        self.ops.apply(self.plan, self.action, self.annotations, {})
        self.assertEqual(self.entity.parentId, 'synParent')
        self.assertEqual(dict(self.entity.annotations), {'species': ['human'], 'disease': 'ALS'})
        self.syn.store.assert_called_once_with(self.entity, forceVersion=False)


if __name__ == '__main__':
    unittest.main()
