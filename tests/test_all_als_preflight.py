"""ALL ALS dictionary/header preflight regressions; no Synapse access."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from synapse_dataset_manager.updates import all_als_preflight as preflight
from synapse_dataset_manager.updates.workflows import all_als


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.policy = self.root / 'policy.yaml'
        self.policy.write_text('version: 1\nforbidden_columns: [date_of_birth, mrn]\n')
        self.date_policy = self.root / 'date_policy.yaml'
        self.date_policy.write_text(
            'version: 1\nallowed_columns:\n  all_files: [collection_date, assessment_date]\n  by_view: {}\n'
        )
        self.settings = {
            'ignored_file_columns': ['Form Name', 'NeuroGUID'],
            'required_columns': {
                'all_files': ['NeuroGUID', 'NeuroSTAmP'],
                'by_view': {'v_ALLALS_AS_ASSEDEMOG': ['nihguid']},
            },
            'phi_pii_columns_file': str(self.policy),
            'date_screening_policy_file': str(self.date_policy),
            'dictionary_views': {
                'v_allals_as_assedemog': {
                    'display_name': 'v_ALLALS_AS_ASSEDEMOG',
                    'fields': {'nihguid', 'sex', 'neurostamp'},
                },
            },
        }

    def file(self, name, headers):
        path = self.root / name
        path.write_text(','.join(headers) + '\n')
        return str(path)

    def validate(self, headers, settings=None):
        path = self.file('v_ALLALS_AS_ASSEDEMOG.csv', headers)
        return preflight.validate(
            {'synStaging': {'v_ALLALS_AS_ASSEDEMOG.csv': {}}},
            {'synStaging': path}, {'synStaging': 'v_ALLALS_AS_ASSEDEMOG'},
            settings or self.settings,
        )

    def test_sparse_and_filled_dictionaries_normalize_identically(self):
        sparse = self.root / 'sparse.csv'
        sparse.write_text('View Name,Field,Description,Values\nv_ALLALS_AS_ASSEDEMOG,nihguid,GUID,NA\n,sex,Sex,NA\n')
        filled = self.root / 'filled.csv'
        filled.write_text('View Name,Field,Description,Values\nv_ALLALS_AS_ASSEDEMOG,nihguid,GUID,NA\nv_ALLALS_AS_ASSEDEMOG,sex,Sex,NA\n')
        self.assertEqual(preflight.load_dictionary(sparse), preflight.load_dictionary(filled))

    def test_technical_and_required_columns(self):
        self.assertEqual(self.validate(['Form Name', 'NeuroGUID', 'NeuroSTAmP', 'nihguid', 'sex']), [])
        with self.assertRaisesRegex(ValueError, 'required headers missing: neurostamp'):
            self.validate(['Form Name', 'NeuroGUID', 'nihguid', 'sex'])
        with self.assertRaisesRegex(ValueError, 'required headers missing: nihguid'):
            self.validate(['Form Name', 'NeuroGUID', 'NeuroSTAmP', 'sex'])

    def test_dictionary_exceptions_warn_without_requiring_legacy_headers(self):
        settings = dict(self.settings)
        settings['ignored_file_columns'] = ['Form Name', 'NeuroGUID', 'NeuroSTAmP', 'visit_name']
        settings['dictionary_exceptions'] = [
            'localUID', 'subjectUID', 'siteUID', 'initials',
            'reason_for_failure', 'state', 'visit',
        ]
        settings['dictionary_views'] = {
            'v_allals_as_assedemog': {
                **self.settings['dictionary_views']['v_allals_as_assedemog'],
                'fields': {
                    'nihguid', 'sex', 'neurostamp', 'localuid', 'subjectuid', 'siteuid',
                    'initials', 'reason_for_failure', 'state', 'visit',
                },
            },
        }
        warnings = self.validate(
            ['Form Name', 'NeuroGUID', 'NeuroSTAmP', 'visit_name', 'nihguid', 'sex'], settings
        )
        self.assertTrue(any('dictionary includes exception field(s): initials, localuid, '
                            'reason_for_failure, siteuid, state, subjectuid, visit' in warning
                            for warning in warnings))

    def test_leading_empty_index_is_warned_but_other_blank_headers_fail(self):
        warnings = self.validate(['', 'Form Name', 'NeuroGUID', 'NeuroSTAmP', 'nihguid', 'sex'])
        self.assertEqual(warnings, ['v_ALLALS_AS_ASSEDEMOG.csv: ignored leading unnamed row-index column'])
        with self.assertRaisesRegex(ValueError, 'cannot contain an empty value'):
            self.validate(['Form Name', '', 'NeuroGUID', 'NeuroSTAmP', 'nihguid', 'sex'])
        no_index = dict(self.settings)
        no_index['allow_leading_empty_index'] = False
        with self.assertRaisesRegex(ValueError, 'cannot contain an empty value'):
            self.validate(['', 'Form Name', 'NeuroGUID', 'NeuroSTAmP', 'nihguid', 'sex'], no_index)

    def test_exact_dictionary_coverage_and_phi_gate(self):
        with self.assertRaisesRegex(ValueError, 'file headers absent from dictionary: unexpected'):
            self.validate(['NeuroGUID', 'NeuroSTAmP', 'nihguid', 'sex', 'unexpected'])
        with self.assertRaisesRegex(ValueError, 'dictionary headers absent from file: sex'):
            self.validate(['NeuroGUID', 'NeuroSTAmP', 'nihguid'])
        with self.assertRaisesRegex(ValueError, 'forbidden PHI/PII headers: date_of_birth'):
            self.validate(['NeuroGUID', 'NeuroSTAmP', 'nihguid', 'sex', 'Date of Birth'])
        policy = Path('configs/phi_pii_columns.yaml')
        self.assertIn('localuid', preflight.load_policy(policy))

    def test_repository_date_policy_has_assess_and_prevent_exemptions(self):
        policy = preflight.load_date_policy(Path('configs/all_als_date_screening.yaml'))
        self.assertTrue({'mh_clin_dat', 'mhevdtyp_diagnosis', 'ecasoc', 'prindc', 'prstdat',
                         'mhterm', 'cdnaloc', 'pralsgt_nr_approxdat', 'dsreasos'}
                        <= policy['by_view_prefix']['v_allals_as'])
        self.assertTrue({'cdnaloc', 'pralsgt_nr_approxdat', 'prstdat', 'ms_rue_nvorres',
                         'ms_rue_othsp'} <= policy['by_view_prefix']['v_allals_pr'])

    def test_date_screening_blocks_dates_and_warns_on_bare_years(self):
        settings = dict(self.settings)
        settings['preflight_report'] = str(self.root / 'preflight.md')
        settings['dictionary_views'] = {
            'v_allals_as_assedemog': {
                **self.settings['dictionary_views']['v_allals_as_assedemog'],
                'fields': {'nihguid', 'sex', 'neurostamp', 'notes', 'assessment_date'},
            },
        }
        path = self.root / 'v_ALLALS_AS_ASSEDEMOG.csv'
        path.write_text(
            'NeuroGUID,NeuroSTAmP,nihguid,sex,notes,assessment_date\n'
            'a,s,g,F,"seen 03/04/2021",2021-03-04\n'
            'b,s,h,M,"diagnosed in 2018",2020-01-01\n'
        )
        with self.assertRaisesRegex(ValueError, 'disallowed date values: notes: 1 cells') as error:
            preflight.validate(
                {'id': {'v_ALLALS_AS_ASSEDEMOG.csv': {}}}, {'id': str(path)},
                {'id': 'v_ALLALS_AS_ASSEDEMOG'}, settings,
            )
        self.assertIn('standalone year warning in notes', str(error.exception))
        report = Path(settings['preflight_report']).read_text()
        self.assertIn('# ALL ALS Preflight Report', report)
        self.assertIn('**Status:** Failed', report)
        self.assertIn('standalone year warning in notes', report)
        self.assertNotIn('diagnosed in 2018', report)
        # A clean file with a standalone year emits a safe, non-blocking warning.
        path.write_text(
            'NeuroGUID,NeuroSTAmP,nihguid,sex,notes,assessment_date\n'
            'b,s,h,M,"diagnosed in 2018",2020-01-01\n'
        )
        warnings = preflight.validate(
            {'id': {'v_ALLALS_AS_ASSEDEMOG.csv': {}}}, {'id': str(path)},
            {'id': 'v_ALLALS_AS_ASSEDEMOG'}, settings,
        )
        self.assertIn('standalone year warning in notes: 1 cells (rows 2)', warnings[0])

    def test_raw_date_values_require_explicit_opt_in(self):
        path = self.root / 'v_ALLALS_AS_ASSEDEMOG.csv'
        path.write_text('NeuroGUID,NeuroSTAmP,nihguid,sex\na,s,g,2020-01-01\n')
        settings = dict(self.settings)
        settings['include_violation_values'] = True
        settings['preflight_report'] = str(self.root / 'unsafe.md')
        with self.assertRaisesRegex(ValueError, "row 2: '2020-01-01'"):
            preflight.validate(
                {'id': {'v_ALLALS_AS_ASSEDEMOG.csv': {}}}, {'id': str(path)},
                {'id': 'v_ALLALS_AS_ASSEDEMOG'}, settings,
            )
        self.assertIn("row 2: '2020-01-01'", Path(settings['preflight_report']).read_text())

    def test_raw_standalone_year_warnings_require_explicit_opt_in(self):
        path = self.root / 'v_ALLALS_AS_ASSEDEMOG.csv'
        path.write_text('NeuroGUID,NeuroSTAmP,nihguid,sex\na,s,g,"diagnosed in 2018"\n')
        settings = dict(self.settings)
        settings['include_violation_values'] = True
        warnings = preflight.validate(
            {'id': {'v_ALLALS_AS_ASSEDEMOG.csv': {}}}, {'id': str(path)},
            {'id': 'v_ALLALS_AS_ASSEDEMOG'}, settings,
        )
        self.assertIn("row 2: 'diagnosed in 2018'", warnings[0])

    def test_all_files_are_analysed_before_preflight_fails(self):
        first = self.root / 'first.csv'
        second = self.root / 'second.csv'
        first.write_text('NeuroGUID,NeuroSTAmP,nihguid,sex,notes\na,s,g,F,2020-01-01\n')
        second.write_text('NeuroGUID,NeuroSTAmP,nihguid\na,s,g\n')
        with self.assertRaisesRegex(ValueError, 'first.csv') as error:
            preflight.validate(
                {'one': {'first.csv': {}}, 'two': {'second.csv': {}}},
                {'one': str(first), 'two': str(second)},
                {'one': 'v_ALLALS_AS_ASSEDEMOG', 'two': 'v_ALLALS_AS_ASSEDEMOG'}, self.settings,
            )
        self.assertIn('second.csv', str(error.exception))
        self.assertIn('disallowed date values', str(error.exception))
        self.assertIn('dictionary headers absent from file: sex', str(error.exception))

    def test_repository_phi_policy_is_valid_and_includes_all_als_fields(self):
        policy = preflight.load_policy(Path('configs/phi_pii_columns.yaml'))
        self.assertTrue({
            'zipcode', 'state', 'othertxt_dvterm', 'dvdesc', 'dvcapa',
            'wbld_lbreasnd', 'wbld_lbdesc', 'seru_lbreasnd', 'seru_lbdesc',
            'plas_lbreasnd', 'plas_lbdesc', 'prdesc', 'rna_lbdesc',
            'emgndna_othsp', 'emgncsna_othsp', 'peov_othsp', 'peov_noclin',
            'describe', 'predisgc_locp', 'predisgc_ppa', 'predisgc_ntothsp',
            'predisgc_tothsp', 'intrvwrgc_suppqs', 'postgpri_comm',
            'postgpri_term', 'gtr_return_in', 'gtr_noreturn_opsc',
            'gtr_resultsotsp', 'gtr_var_nocoval', 'postdisgc_ppa',
            'reasnd_weight', 'tele_occur_context',
        } <= policy)

    def test_missing_view_duplicate_headers_and_policy_conflicts_fail_closed(self):
        path = self.file('unknown.csv', ['NeuroGUID', 'NeuroSTAmP'])
        with self.assertRaisesRegex(ValueError, 'no data-dictionary view'):
            preflight.validate({'id': {'unknown.csv': {}}}, {'id': path}, {'id': 'unknown'}, self.settings)
        with self.assertRaisesRegex(ValueError, 'duplicate normalized'):
            self.file('duplicate.csv', ['Form Name', 'form_name'])
            preflight.read_headers(self.root / 'duplicate.csv')
        conflicting = dict(self.settings)
        conflicting['required_columns'] = {'all_files': ['MRN'], 'by_view': {}}
        with self.assertRaisesRegex(ValueError, 'conflicts with PHI/PII'):
            self.validate(['NeuroGUID', 'NeuroSTAmP', 'nihguid', 'sex'], conflicting)
        missing_policy = dict(self.settings)
        missing_policy['phi_pii_columns_file'] = str(self.root / 'gone.yaml')
        with self.assertRaisesRegex(ValueError, 'policy file not found'):
            self.validate(['NeuroGUID', 'NeuroSTAmP', 'nihguid', 'sex'], missing_policy)

    def test_repeated_field_rows_define_permissible_values(self):
        path = self.root / 'values.csv'
        path.write_text(
            'View Name,Field,Description,Values\n'
            'v_ALLALS_AS_ASSEAELOG,aeyn,Age at event,NA\n'
            ',aeyn,Not applicable,NA\n'
            ',aeyn,Yes,1\n'
            ',aeyn,No,2\n'
        )
        dictionary = preflight.load_dictionary(path)
        definition = dictionary['v_allals_as_asseaelog']['definitions']['aeyn']
        self.assertEqual(definition['description'], 'Age at event')
        self.assertEqual(definition['values'], {'NA': 'Not applicable', '1': 'Yes', '2': 'No'})
        self.assertEqual(definition['ambiguous_values'], {})
        self.assertEqual(dictionary['v_allals_as_asseaelog']['fields'], {'aeyn'})

    def test_dictionary_rejects_bad_structure(self):
        path = self.root / 'bad.csv'
        path.write_text('View Name,Field,Description,Values\n,nihguid,GUID,NA\n')
        with self.assertRaisesRegex(ValueError, 'before a view'):
            preflight.load_dictionary(path)
        path.write_text('View Name,Field,Description,Values\nv,age,Age,NA\nv,age,Again,\n')
        with self.assertRaisesRegex(ValueError, 'has no value code'):
            preflight.load_dictionary(path)
        path.write_text('View Name,Field,Description,Values\nv,age,Age,NA\nv,age,Not applicable,NA\nv,age,Not applicable,NA\n')
        dictionary = preflight.load_dictionary(path)
        self.assertEqual(len(dictionary['v']['warnings']), 1)
        self.assertIn('duplicate value/description', dictionary['v']['warnings'][0])
        path.write_text('View Name,Field,Description,Values\nv,age,Age,NA\nv,age,Not applicable,NA\nv,age,Missing,NA\n')
        dictionary = preflight.load_dictionary(path)
        definition = dictionary['v']['definitions']['age']
        self.assertNotIn('NA', definition['values'])
        self.assertEqual(definition['ambiguous_values']['NA'], ['Not applicable', 'Missing'])
        path.write_text('View Name,Field,Description,Values\nv,age,Age,NA\nv,age,Yes,1\nv,age,Again,1\n')
        with self.assertRaisesRegex(ValueError, 'conflicting descriptions'):
            preflight.load_dictionary(path)
        path.write_text('View Name,Field,Description,Values\nv,age,Age,NA\nv,sex,Sex,NA\nv,age,Yes,1\n')
        with self.assertRaisesRegex(ValueError, 'non-contiguous'):
            preflight.load_dictionary(path)

    def test_current_layout_mapping_parser_omits_ambiguous_na_values(self):
        from synapse_dataset_manager import cli
        path = self.root / 'ambiguous_mapping.csv'
        path.write_text(
            'View Name,Field,Description,Values\n'
            'v_ALLALS_AS_ASSEAELOG,aeyn,Age at event,NA\n'
            ',aeyn,Not applicable,NA\n'
            ',aeyn,Missing,NA\n'
            ',aeyn,Yes,1\n'
        )
        parsed = cli.parse_data_dictionary(str(path))
        self.assertNotIn('NA', parsed['aeyn']['values'])
        self.assertEqual(parsed['aeyn']['ambiguous_values']['NA'], ['Not applicable', 'Missing'])
        self.assertEqual(parsed['aeyn']['values']['1'], 'Yes')

    def test_current_layout_mapping_parser_retains_coded_values(self):
        from synapse_dataset_manager import cli
        path = self.root / 'mapping.csv'
        path.write_text(
            'View Name,Field,Description,Values\n'
            'v_ALLALS_AS_ASSEAELOG,aeyn,Age at event,NA\n'
            ',aeyn,Not applicable,NA\n'
            ',aeyn,Yes,1\n'
            ',aeyn,No,2\n'
        )
        parsed = cli.parse_data_dictionary(str(path))
        self.assertEqual(parsed['aeyn']['description'], 'Age at event')
        self.assertEqual(parsed['aeyn']['values'], {'NA': 'Not applicable', '1': 'Yes', '2': 'No'})

    def test_all_als_prepare_prints_dictionary_warnings(self):
        data_dict = self.root / 'warning_dictionary.csv'
        data_dict.write_text(
            'View Name,Field,Description,Values\n'
            'v_ALLALS_AS_ASSEDEMOG,nihguid,GUID,NA\n'
            ',nihguid,Not applicable,NA\n'
            ',nihguid,Not applicable,NA\n'
            ',sex,Sex,NA\n'
            ',NeuroSTAmP,Stamp,NA\n'
        )
        staged_file = self.file('warning_stage.csv', ['NeuroGUID', 'NeuroSTAmP', 'nihguid', 'sex'])
        services = Mock()
        services.build_staging_form_map.return_value = ({}, {'staging': 'form.csv'},
                                                         {'staging': staged_file},
                                                         {'staging': 'v_ALLALS_AS_ASSEDEMOG'})
        with patch('builtins.print') as output:
            all_als.prepare(None, {'staging': {'v_ALLALS_AS_ASSEDEMOG.csv': {}}}, str(self.root), {
                'data_dict_path': str(data_dict),
                'all_als': {'phi_pii_columns_file': str(self.policy)},
            }, services)
        self.assertTrue(any('dictionary warning' in str(call) for call in output.call_args_list))

    def test_prevent_uses_its_configured_demographics_view_not_assess_default(self):
        data_dict = self.root / 'prevent_dictionary.csv'
        data_dict.write_text(
            'View Name,Field,Description,Values\n'
            'v_ALLALS_PR_PREVDEMOG,nihguid,GUID,NA\n'
            ',sex,Sex,NA\n'
            ',NeuroSTAmP,Stamp,NA\n'
        )
        staged_file = self.file('prevent_stage.csv', ['NeuroGUID', 'NeuroSTAmP', 'nihguid', 'sex'])
        services = Mock()
        services.build_staging_form_map.return_value = ({}, {'staging': 'form.csv'},
                                                         {'staging': staged_file},
                                                         {'staging': 'v_ALLALS_PR_PREVDEMOG'})
        result = all_als.prepare(None, {'staging': {'v_ALLALS_PR_PREVDEMOG.csv': {}}}, str(self.root), {
            'data_dict_path': str(data_dict),
            'all_als': {
                'phi_pii_columns_file': str(self.policy),
                'required_columns': {'by_view': {'v_ALLALS_PR_PREVDEMOG': ['nihguid']}},
            },
        }, services)
        self.assertEqual(result[2], {'staging': 'v_ALLALS_PR_PREVDEMOG'})

    def test_all_als_prepare_requires_dictionary_and_runs_preflight(self):
        staging = {'staging': {'v_ALLALS_AS_ASSEDEMOG.csv': {}}}
        services = Mock()
        with self.assertRaisesRegex(ValueError, 'requires --data-dict'):
            all_als.prepare(None, staging, str(self.root), {}, services)
        data_dict = self.root / 'dictionary.csv'
        data_dict.write_text('View Name,Field,Description,Values\nv_ALLALS_AS_ASSEDEMOG,nihguid,GUID,NA\nv_ALLALS_AS_ASSEDEMOG,sex,Sex,NA\nv_ALLALS_AS_ASSEDEMOG,NeuroSTAmP,Stamp,NA\n')
        staged_file = self.file('stage.csv', ['NeuroGUID', 'NeuroSTAmP', 'nihguid', 'sex'])
        services.build_staging_form_map.return_value = ({}, {'staging': 'form.csv'},
                                                         {'staging': staged_file},
                                                         {'staging': 'v_ALLALS_AS_ASSEDEMOG'})
        result = all_als.prepare(None, staging, str(self.root), {
            'data_dict_path': str(data_dict),
            'all_als': {'phi_pii_columns_file': str(self.policy)},
        }, services)
        self.assertEqual(result[0], {'staging': 'form.csv'})


if __name__ == '__main__':
    unittest.main()
