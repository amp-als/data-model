import unittest

from synapse_dataset_manager.cli import is_metadata_schema_file


class MetadataSchemaFileDetectionTests(unittest.TestCase):
    def test_data_dictionary_filename_uses_metadata_schema(self):
        self.assertTrue(is_metadata_schema_file('Data_Dictionary_ALLALS_PREVENT.csv'))

    def test_structural_metadata_annotation_uses_metadata_schema(self):
        self.assertTrue(is_metadata_schema_file('unrelated.csv', {
            'dataType': ['Structural Metadata'],
        }))

    def test_clinical_file_is_not_metadata_schema(self):
        self.assertFalse(is_metadata_schema_file('Demographics.csv', {
            'dataType': ['clinical'],
        }))


if __name__ == '__main__':
    unittest.main()
