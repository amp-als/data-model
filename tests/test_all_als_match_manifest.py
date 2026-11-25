"""ALL ALS reviewed match-manifest regressions."""

import json
from pathlib import Path
import tempfile
import unittest

from synapse_dataset_manager.updates import all_als_match_manifest as manifests


class Entity(dict):
    def __init__(self, entity_id, name):
        super().__init__(etag=f'etag-{entity_id}', versionNumber=1)
        self.name = name


class Syn:
    def __init__(self):
        self.entities = {
            'dataset': Entity('dataset', 'Dataset'),
            'target': Entity('target', 'Eligibility Criteria 2.csv'),
            'source': Entity('source', 'v_RAW_GEN2.csv'),
        }

    def get(self, entity_id, downloadFile=False):
        if entity_id not in self.entities:
            self.entities[entity_id] = Entity(entity_id, f'{entity_id}.csv')
        return self.entities[entity_id]


class Services:
    @staticmethod
    def _norm_filename_for_match(name):
        return name.lower().replace('.csv', '').strip()


class MatchManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'match.json'
        self.syn = Syn()
        self.existing = {'target': {'Eligibility Criteria 2.csv': {'viewName': ['v_CANON_GEN2']}}}
        self.staging = {'source': {'v_RAW_GEN2.csv': {}}}
        self.names = {'source': 'Eligibility Criteria 2.csv'}
        self.groups = {'source': 'v_RAW_GEN2'}
        self.aliases = {'v_raw_gen2': 'v_canon_gen2'}

    def test_first_pass_writes_draft_then_approved_manifest_matches(self):
        with self.assertRaises(manifests.MatchManifestReviewRequired):
            manifests.resolve_manifest(self.path, 'dataset', self.existing, self.staging,
                                       self.names, self.groups, self.aliases, Services(), self.syn)
        draft = json.loads(self.path.read_text())
        self.assertEqual(draft['status'], 'draft')
        self.assertEqual(draft['mappings'][0]['source_synapse_id'], 'source')
        draft['status'] = 'approved'
        self.path.write_text(json.dumps(draft))
        self.assertEqual(
            manifests.resolve_manifest(self.path, 'dataset', self.existing, self.staging,
                                       self.names, self.groups, self.aliases, Services(), self.syn),
            {'target': 'source'},
        )

    def test_shared_canonical_view_is_ambiguous_without_exact_form(self):
        self.names['source'] = 'another form.csv'
        self.staging['other'] = {'other.csv': {}}
        self.names['other'] = 'different form.csv'
        self.groups['other'] = 'v_CANON_GEN2'
        with self.assertRaises(manifests.MatchManifestReviewRequired):
            manifests.resolve_manifest(self.path, 'dataset', self.existing, self.staging,
                                       self.names, self.groups, self.aliases, Services(), self.syn)
        draft = json.loads(self.path.read_text())
        self.assertEqual(len(draft['ambiguous']), 1)


if __name__ == '__main__':
    unittest.main()
