"""Offline identity, dictionary, and update integration regressions."""

import argparse
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from synapse_dataset_manager import cli
from synapse_dataset_manager.updates.workflows import get_workflow, general
from synapse_dataset_manager.updates.dictionaries import build_mapping, apply_group_annotations


def files(**entries):
    return {sid: {name: {}} for sid, name in entries.items()}


class IdentityTests(unittest.TestCase):
    def test_defaults_never_download(self):
        services = Mock()
        staging = files(syn1='a.csv')
        self.assertEqual(general.prepare(None, staging, '.', {}, services),
                         ({'syn1': 'a.csv'}, {}, {}, {}))
        services.download_file_for_analysis.assert_not_called()

    def test_exact_only_and_no_view_fallback(self):
        existing = {'old': {'Subject-Data.csv': {'viewName': 'subject_data'}}}
        staging = files(new='subject_data.csv')
        self.assertEqual(general.match(existing, staging, {'new': 'subject_data.csv'},
                                       {'new': 'subject_data'}, {}, Mock()), {})

    def test_ambiguous_targets_rejected(self):
        for existing, names in [
            (files(a='x.csv', b='x.csv'), {'c': 'x.csv'}),
            (files(a='x.csv'), {'c': 'x.csv', 'd': 'x.csv'}),
        ]:
            with self.assertRaises(ValueError):
                general.match(existing, {}, names, {}, {}, Mock())

    def test_explicit_and_same_id_matching(self):
        existing = files(a='old.csv', b='b.csv')
        self.assertEqual(general.match(existing, {}, {'c': 'new.csv', 'b': 'changed.csv'},
                                       {}, {'c': 'a'}, Mock()), {'a': 'c', 'b': 'b'})
        with self.assertRaises(ValueError):
            general.match(existing, {}, {'c': 'x.csv'}, {}, {'c': 'missing'}, Mock())

    def test_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'identity.csv'
            path.write_text('source_filename,release_filename,target_synapse_id,dictionary_group\n'
                            'export.csv,participants.csv,synOld,participants\n')
            result = general.prepare(None, files(synNew='export.csv'), directory,
                                     {'identity_manifest': str(path)}, Mock())
            self.assertEqual(result, ({'synNew': 'participants.csv'}, {},
                                      {'synNew': 'participants'}, {'synNew': 'synOld'}))

    def test_extracted_name_unique_and_extension_preserved(self):
        services = Mock()
        services.download_file_for_analysis.return_value = '/tmp/input.csv'
        services.load_metadata_file.return_value = [{'Name': 'visits'}, {'Name': 'visits'}]
        result = general.prepare(None, files(a='export.csv'), '.', {'name_column': 'Name'}, services)
        self.assertEqual(result[0], {'a': 'visits.csv'})
        services.load_metadata_file.return_value.append({'Name': 'labs'})
        with self.assertRaises(ValueError):
            general.prepare(None, files(a='export.csv'), '.', {'name_column': 'Name'}, services)

    def test_all_als_uses_form_extraction(self):
        services = Mock()
        services.build_staging_form_map.return_value = ({}, {'a': 'Form.csv'}, {}, {'a': 'view'})
        workflow = get_workflow('all_als')
        with patch('synapse_dataset_manager.updates.workflows.all_als.all_als_preflight.load_dictionary',
                   return_value={'view': {'display_name': 'view', 'fields': set()}}), \
             patch('synapse_dataset_manager.updates.workflows.all_als.all_als_preflight.validate') as validate:
            self.assertEqual(workflow.prepare(None, files(a='raw.csv'), '/tmp', {
                'data_dict_path': '/tmp/dictionary.csv',
                'all_als': {'phi_pii_columns_file': '/tmp/policy.yaml'},
            }, services), ({'a': 'Form.csv'}, {}, {'a': 'view'}, {}))
        services.build_staging_form_map.assert_called_once_with(
            None, files(a='raw.csv'), '/tmp', extract_form_names=True,
        )
        validate.assert_called_once()

    def test_all_als_view_disambiguation(self):
        workflow = get_workflow('all_als')
        existing = {'old': {'Form.csv': {'viewName': ['v2']}}}
        staging = files(s1='v1.csv', s2='v2.csv')
        names = {'s1': 'Form.csv', 's2': 'Form.csv'}
        self.assertEqual(workflow.match(existing, staging, names,
                                       {'s1': 'v1', 's2': 'v2'}, {}, cli), {'old': 's2'})
        with self.assertRaises(ValueError):
            workflow.match(files(old='Form.csv'), staging, names,
                           {'s1': 'v1', 's2': 'v2'}, {}, cli)

    def test_manifest_duplicate_sources_and_unsafe_names(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'identity.csv'
            for content in (
                'source_synapse_id,release_filename\na,x.csv\na,y.csv\n',
                'source_synapse_id,release_filename\na,../x.csv\n',
            ):
                path.write_text(content)
                with self.assertRaises(ValueError):
                    general.prepare(None, files(a='export.csv'), directory,
                                    {'identity_manifest': str(path)}, Mock())

    def test_registry_explicit(self):
        self.assertIs(get_workflow('general'), general)
        with self.assertRaises(ValueError):
            get_workflow('/tmp/custom.py')


class DictionaryTests(unittest.TestCase):
    def test_custom_columns_and_groups(self):
        mapping = build_mapping('unused', {'dictionary_group_column': 'Table',
                                          'dictionary_field_column': 'Variable'},
                                lambda _: [{'Table': 'patients', 'Variable': 'id'}])
        self.assertEqual(mapping['_groups'], {'patients': {}})
        self.assertNotIn('_views', mapping)
        self.assertIn('id', mapping)

    def test_group_mapping_round_trip_and_merge(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'mapping.dict')
            mapping = {'_groups': {'a': {'species': 'human'}}}
            with contextlib.redirect_stdout(io.StringIO()):
                cli.write_mapping_file(path, mapping)
                self.assertEqual(cli.load_mapping_dict(path), mapping)
                merged = cli.merge_into_existing_mapping(path, {'_groups': {'a': {}, 'b': {}}})
            self.assertEqual(merged['_groups'], {'a': {'species': 'human'}, 'b': {}})

    def test_missing_columns_fail(self):
        with self.assertRaises(ValueError):
            build_mapping('unused', {'dictionary_group_column': 'Table'},
                          lambda _: [{'Field': 'id'}])

    def test_group_annotations_exact_and_preserve_existing(self):
        mapping = {'_groups': {'Patients': {'species': 'human', 'disease': 'ALS'}}}
        original = {'species': 'mouse', 'disease': ''}
        self.assertEqual(apply_group_annotations(original, 'Patients', mapping),
                         {'species': 'mouse', 'disease': 'ALS'})
        self.assertEqual(apply_group_annotations(original, 'patients', mapping), original)


class WorkflowIntegrationTests(unittest.TestCase):
    def test_general_phase_one_generated_output(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Mock(ANNOTATIONS_DIR=directory, SCHEMA_BASE_PATH='unused',
                          FIELD_MIGRATIONS_PATH='unused', VERBOSE=False)
            config.get_dataset_config.return_value = {}
            syn = Mock()
            syn.get.return_value.name = 'Example'
            args = argparse.Namespace(dataset_id='dataset', staging_folder=['folder'])
            with contextlib.ExitStack() as stack:
                for name, value in {
                    'get_all_schemas': {}, 'connect_to_synapse': syn,
                    'enumerate_dataset_files': files(old='participants.csv'),
                    'enumerate_folder_files': files(new='participants.csv', added='visits.csv'),
                    'load_field_migrations': {}, 'detect_file_type': 'File',
                    'create_annotation_template': {}, 'get_field_type_map': {},
                }.items():
                    stack.enter_context(patch.object(cli, name, return_value=value))
                download = stack.enter_context(patch.object(cli, 'download_file_for_analysis'))
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                cli.handle_update_workflow(args, config)
                download.assert_not_called()
            generated = json.loads((Path(directory) / 'Example_update_annotations.json').read_text())
            self.assertEqual(generated['old']['participants.csv']['_staging_id'], 'new')
            self.assertEqual(generated['added']['visits.csv']['_staging_id'], 'added')

    def test_phase_two_preflight_prevents_writes(self):
        for conflict in (True, False):
            with self.subTest(conflicting_sources=conflict), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'annotations.json'
                annotations = ({'old': {'a.csv': {'_staging_id': 'staged'}}}
                               if conflict else files(added='a.csv'))
                path.write_text(json.dumps(annotations))
                config = Mock(DRY_RUN=False, VERBOSE=False)
                config.get_dataset_config.return_value = {}
                args = argparse.Namespace(dataset_id='dataset', annotations_file=str(path),
                                          skip_validation=True,
                                          local_files_dir='/tmp' if conflict else None)
                with contextlib.ExitStack() as stack:
                    for name, value in {
                        'get_all_schemas': {}, 'connect_to_synapse': Mock(),
                        'enumerate_dataset_files': files(old='a.csv'),
                    }.items():
                        stack.enter_context(patch.object(cli, name, return_value=value))
                    backend = stack.enter_context(patch(
                        'synapse_dataset_manager.updates.operations.SynapseOperations'))
                    stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                    with self.assertRaises(ValueError):
                        cli.handle_update_workflow(args, config)
                    backend.return_value.apply.assert_not_called()

    def test_verification_failure_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'annotations.json'
            path.write_text(json.dumps(files(old='a.csv')))
            config = Mock(DRY_RUN=False, VERBOSE=False)
            config.get_dataset_config.return_value = {}
            args = argparse.Namespace(dataset_id='dataset', annotations_file=str(path),
                                      skip_validation=True)
            with contextlib.ExitStack() as stack:
                for name, value in {
                    'get_all_schemas': {}, 'connect_to_synapse': Mock(),
                    'enumerate_dataset_files': files(old='a.csv'),
                }.items():
                    stack.enter_context(patch.object(cli, name, return_value=value))
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                runner = stack.enter_context(patch(
                    'synapse_dataset_manager.updates.engine.run_update',
                    side_effect=RuntimeError('Update incomplete'),
                ))
                with self.assertRaisesRegex(RuntimeError, 'Update incomplete'):
                    cli.handle_update_workflow(args, config)
                runner.assert_called_once()


if __name__ == '__main__':
    unittest.main()
