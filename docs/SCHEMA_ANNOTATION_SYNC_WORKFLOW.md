# Schema Annotation Sync Workflow

When the data model schema changes, existing Synapse annotations may no longer match the current JSON Schemas. Use the `sync-dataset-schema-annotations` workflow in `synapse_dataset_manager.py` to validate and incrementally update metadata without downloading dataset/file contents.

## Goals

- Validate current Synapse dataset-level annotations against current schemas.
- Optionally validate file-level annotations for files referenced by each Dataset.
- Generate reviewable reports and merged annotation templates.
- Apply only reviewed annotation deltas after human approval.
- Avoid downloading actual dataset files; this workflow uses Synapse metadata, annotations, Dataset membership, and optionally wiki/publication metadata only.

## Environment

Use the `amp-als` environment for Synapse client access:

```bash
mamba run -n amp-als python synapse_dataset_manager.py <command>
```

## Dataset-Level Validation

Validate all Datasets in the configured DatasetCollection or a specified collection:

```bash
mamba run -n amp-als python synapse_dataset_manager.py sync-dataset-schema-annotations \
  --collection-id syn66496326 \
  --dry-run
```

Outputs default to:

```text
annotations/dataset_schema_sync/
├── schema_validation_report.json
├── schema_validation_report.csv
├── schema_merged_annotation_templates.json      # current annotations + schema fields
├── schema_missing_annotation_templates.json     # only fields missing from Synapse
└── schema_update_deltas_to_apply.json
```

Use `--output-dir` to write to a different location.

Template output can be controlled with `--template-mode`:

```bash
--template-mode merged   # existing Synapse annotations plus blank values for missing schema fields
--template-mode missing  # only missing schema fields, useful for curation/fill-in work
--template-mode both     # default
```

In this workflow, **missing** means either:

1. the field exists in the local/current JSON Schema but is not present in Synapse annotations, or
2. the field exists in Synapse annotations but is not filled in, e.g. `""`, `[""]`, `[]`, or `null`.

So `schema_missing_annotation_templates.json` is a fill-in template for schema-defined fields that Synapse does not currently have populated.

## File-Level Validation

To also validate file annotations for files referenced by each Dataset:

```bash
mamba run -n amp-als python synapse_dataset_manager.py sync-dataset-schema-annotations \
  --collection-id syn66496326 \
  --include-files \
  --dry-run
```

Additional outputs:

```text
file_schema_validation_report.json
file_schema_validation_report.csv
file_schema_merged_annotation_templates.json     # when --template-mode merged/both
file_schema_missing_annotation_templates.json    # when --template-mode missing/both
```

This enumerates Dataset rows and reads file annotations only. It does **not** download file contents.

## Applying Reviewed Deltas

Prepare a reviewed delta file keyed by Synapse ID. Supported shape:

```json
{
  "syn123": {
    "Dataset Name": {
      "cohortType": ["Case-Control"],
      "cohort_count": 2,
      "study_count": 1,
      "_review_status": "approved"
    }
  }
}
```

Preview updates:

```bash
mamba run -n amp-als python synapse_dataset_manager.py sync-dataset-schema-annotations \
  --collection-id syn66496326 \
  --updates-file annotations/dataset_collection_update/proposed_dataset_annotation_deltas.json \
  --dry-run
```

Apply after review:

```bash
mamba run -n amp-als python synapse_dataset_manager.py sync-dataset-schema-annotations \
  --collection-id syn66496326 \
  --updates-file annotations/dataset_collection_update/proposed_dataset_annotation_deltas.json \
  --execute
```

To require explicit approval, add:

```bash
--require-approved
```

Only records with `_review_status: "approved"` will be considered.

## Current Cohort Annotation Use Case

The recent schema update added required dataset-level fields:

- `cohortType`
- `cohort_count`
- `study_count`

Workflow:

1. Regenerate schemas after model changes:
   ```bash
   mamba run -n amp-als make Dataset ClinicalDataset OmicDataset
   ```
2. Validate current Synapse annotations:
   ```bash
   mamba run -n amp-als python synapse_dataset_manager.py sync-dataset-schema-annotations \
     --collection-id syn66496326 \
     --dry-run
   ```
3. Review missing fields in `schema_validation_report.csv`.
4. Build/fill reviewed deltas for only the missing fields.
5. Dry-run with `--updates-file`.
6. Execute only after review.

## Notes / Future Improvements

- Current validation normalizes single-value Synapse annotation lists to scalar values for schema validation where the schema expects scalars.
- Older annotations may still fail validation due to legacy enum values or type conventions. Do not blindly reset full annotations until those legacy values are reviewed.
- Prefer incremental deltas over full annotation replacement.
- For file-level schema changes, use `--include-files` first to measure impact before creating update deltas.
