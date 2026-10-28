"""Plan-driven execution tests; all remote operations use an in-memory backend."""

import argparse
import contextlib
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from synapse_dataset_manager import cli

from synapse_dataset_manager.updates.engine import run_update
from synapse_dataset_manager.updates.plans import build_plan, load_plan


FILE = 'org.sagebionetworks.repo.model.FileEntity'


class FakeBackend:
    def __init__(self):
        self.states = {}
        for entity_id, name in [('dataset', 'Dataset'), ('a', 'a.csv'), ('b', 'b.csv'),
                                ('source', 'source.csv'), ('release', 'Released')]:
            self.states[entity_id] = {
                'id': entity_id, 'etag': '1', 'name': name, 'parentId': 'parent',
                'versionNumber': 1, 'versionLabel': None, 'dataFileHandleId': 'handle-' + entity_id,
                'concreteType': FILE, 'annotations_sha256': 'original',
            }
        self.states['release']['concreteType'] = 'org.sagebionetworks.repo.model.Folder'
        self.references = [{'id': 'a', 'version': 1}, {'id': 'b', 'version': 1}]
        self.occupants = []
        self.writes = []
        self.prepared = False
        self.fail_target = None
        self.verify_fail_target = None
        self.change_during_prepare = False

    def snapshot(self, entity_id):
        return deepcopy(self.states[entity_id])

    def members(self, dataset_id):
        return deepcopy(self.references)

    def children(self, folder_id):
        return deepcopy(self.occupants)

    def prepare_content(self, plan, directory):
        self.prepared = True
        if self.change_during_prepare:
            self.states['source']['etag'] = 'changed'
        return {}

    def apply(self, plan, action, annotations, paths):
        target = action['target_id']
        self.writes.append(target)
        if self.fail_target == target:
            raise RuntimeError('simulated remote failure')
        self.states[target]['etag'] += '-written'

    def verify(self, plan, action, annotations):
        return ['simulated verification failure'] if action['target_id'] == self.verify_fail_target else []

    def verify_dataset(self, plan, observed=None):
        return []


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self.annotations = {'a': {'a.csv': {'species': ['human'], '_staging_id': 'source'}}}
        self.options = {'local_files_dir': None, 'release_folder': None,
                        'version_label': 'v2', 'version_comment': 'Release', 'skip_validation': False}
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = str(Path(self.directory.name) / 'review.json')
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def run_engine(self, **kwargs):
        return run_update(self.backend, 'dataset', 'general', self.annotations, self.options, **kwargs)

    def review(self):
        result = self.run_engine(dry_run=True, write_plan_file=self.path)
        self.assertEqual(result['status'], 'dry_run')
        self.assertFalse(self.backend.prepared)
        self.assertEqual(self.backend.writes, [])
        return load_plan(self.path)

    def test_review_then_execute(self):
        plan = self.review()
        self.assertEqual(plan['actions'][0]['kind'], 'version_staging')
        self.assertTrue(plan['actions'][0]['refresh_membership'])
        result = self.run_engine(dry_run=False, plan_file=self.path)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['actions'][0]['status'], 'verified')
        self.assertEqual(self.backend.writes, ['a'])
        self.assertEqual(json.loads(Path(self.path + '.results.json').read_text()), result)

    def test_cli_dry_run_then_reviewed_apply(self):
        annotations_path = Path(self.directory.name) / 'annotations.json'
        annotations_path.write_text(json.dumps(self.annotations))
        args = argparse.Namespace(dataset_id='dataset', annotations_file=str(annotations_path),
                                  skip_validation=True)
        config = Mock(DRY_RUN=True, VERBOSE=False)
        config.get_dataset_config.return_value = {}
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(cli, 'get_all_schemas', return_value={}))
            stack.enter_context(patch.object(cli, 'connect_to_synapse', return_value=Mock()))
            stack.enter_context(patch('synapse_dataset_manager.updates.operations.SynapseOperations',
                                      return_value=self.backend))
            result = cli.handle_update_workflow(args, config)
            self.assertEqual(result['status'], 'dry_run')
            args.plan_file = str(annotations_path.with_suffix('.plan.json'))
            self.assertTrue(Path(args.plan_file).is_file())
            config.DRY_RUN = False
            result = cli.handle_update_workflow(args, config)
            self.assertEqual(result['status'], 'complete')
            self.assertEqual(self.backend.writes, ['a'])

    def test_execute_requires_review(self):
        with self.assertRaisesRegex(ValueError, 'reviewed'):
            self.run_engine(dry_run=False)
        self.assertEqual(self.backend.writes, [])

    def test_review_does_not_overwrite(self):
        self.review()
        with self.assertRaises(FileExistsError):
            self.review()

    def test_stale_entities_membership_and_annotations_block_all_writes(self):
        mutations = [
            lambda: self.backend.states['a'].update(etag='changed'),
            lambda: self.backend.states['source'].update(versionNumber=2),
            lambda: self.backend.states['a'].update(annotations_sha256='changed'),
            lambda: self.backend.references.append({'id': 'source', 'version': 1}),
            lambda: self.backend.references[0].update(version=2),
            lambda: self.annotations['a']['a.csv'].update(species=['mouse']),
            lambda: self.options.update(version_label='v3'),
            lambda: self.options.update(skip_validation=True),
        ]
        original_states = deepcopy(self.backend.states)
        original_refs = deepcopy(self.backend.references)
        original_annotations = deepcopy(self.annotations)
        original_options = deepcopy(self.options)
        self.review()
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                self.backend.states = deepcopy(original_states)
                self.backend.references = deepcopy(original_refs)
                self.annotations = deepcopy(original_annotations)
                self.options = deepcopy(original_options)
                mutate()
                with self.assertRaisesRegex(ValueError, 'Stale|mismatched'):
                    self.run_engine(dry_run=False, plan_file=self.path)
                self.assertEqual(self.backend.writes, [])

    def test_stale_after_download_blocks_all_writes(self):
        self.review()
        self.backend.change_during_prepare = True
        with self.assertRaisesRegex(ValueError, 'Stale'):
            self.run_engine(dry_run=False, plan_file=self.path)
        self.assertEqual(self.backend.writes, [])

    def test_local_file_changes_and_missing_files(self):
        self.annotations['a']['a.csv'].pop('_staging_id')
        self.options['local_files_dir'] = self.directory.name
        path = Path(self.directory.name) / 'a.csv'
        path.write_text('original')
        plan = self.review()
        self.assertEqual(plan['actions'][0]['kind'], 'version_local')
        path.write_text('changed')
        with self.assertRaisesRegex(ValueError, 'Stale'):
            self.run_engine(dry_run=False, plan_file=self.path)
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'No local file'):
            self.run_engine(dry_run=False, plan_file=self.path)
        self.assertEqual(self.backend.writes, [])

    def test_partial_failure_report_and_stop(self):
        self.annotations['b'] = {'b.csv': {}}
        self.review()
        self.backend.fail_target = 'a'
        with self.assertRaisesRegex(RuntimeError, 'Update incomplete'):
            self.run_engine(dry_run=False, plan_file=self.path)
        report = json.loads(Path(self.path + '.results.json').read_text())
        self.assertEqual(report['status'], 'incomplete')
        self.assertEqual(report['actions'][0]['status'], 'failed_or_partial')
        self.assertEqual(report['actions'][1]['status'], 'not_started')
        self.assertEqual(self.backend.writes, ['a'])
        with self.assertRaisesRegex(ValueError, 'report already exists'):
            self.run_engine(dry_run=False, plan_file=self.path)

    def test_verification_failure_is_fatal(self):
        self.review()
        self.backend.verify_fail_target = 'a'
        with self.assertRaisesRegex(RuntimeError, 'verification failure'):
            self.run_engine(dry_run=False, plan_file=self.path)
        report = json.loads(Path(self.path + '.results.json').read_text())
        self.assertEqual(report['actions'][0]['verification_failures'], ['simulated verification failure'])

    def test_tampered_plan_rejected(self):
        self.review()
        plan = json.loads(Path(self.path).read_text())
        plan['actions'][0]['target_id'] = 'b'
        Path(self.path).write_text(json.dumps(plan))
        with self.assertRaisesRegex(ValueError, 'edited or corrupted'):
            self.run_engine(dry_run=False, plan_file=self.path)
        self.assertEqual(self.backend.writes, [])

    def test_addition_requires_folder_and_checks_name_collision(self):
        self.annotations = {'source': {'source.csv': {'_staging_id': 'source'}}}
        with self.assertRaisesRegex(ValueError, 'release-folder'):
            self.run_engine(dry_run=True, write_plan_file=self.path)
        self.options['release_folder'] = 'release'
        self.backend.occupants = [{'id': 'other', 'name': 'source.csv'}]
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.run_engine(dry_run=True, write_plan_file=self.path)
        self.backend.occupants = []
        plan = self.review()
        self.assertEqual(plan['actions'][0]['kind'], 'add')
        self.assertEqual(plan['actions'][0]['destination'], 'release')

    def test_conflicting_sources_and_reused_sources_rejected(self):
        self.options['local_files_dir'] = self.directory.name
        with self.assertRaisesRegex(ValueError, 'Cannot combine'):
            self.run_engine(dry_run=True, write_plan_file=self.path)
        self.options['local_files_dir'] = None
        self.annotations['b'] = {'b.csv': {'_staging_id': 'source'}}
        with self.assertRaisesRegex(ValueError, 'reused'):
            self.run_engine(dry_run=True, write_plan_file=self.path)

    def test_unknown_version_and_malformed_artifacts_rejected(self):
        Path(self.path).write_text(json.dumps({'format_version': 999}))
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            load_plan(self.path)
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            build_plan(self.backend, 'dataset', 'general', {'a': {}}, self.options)


if __name__ == '__main__':
    unittest.main()
