# CSV and XLSX Annotation Templates

`generate-template` and `generate-file-templates` can export JSON (the default), CSV,
or Excel (`.xlsx`) templates. XLSX templates provide dropdowns for every enum defined
by the generated JSON Schema.

All commands run in the `amp-als` environment:

```bash
mamba run -n amp-als python synapse_dataset_manager.py <command> ...
```

## Dataset templates

```bash
# Spreadsheet with schema enum dropdowns
mamba run -n amp-als python synapse_dataset_manager.py generate-template \
  --type Clinical --format xlsx \
  --output annotations/clinical_dataset_template.xlsx

# A simple portable CSV template (CSV cannot contain dropdowns)
mamba run -n amp-als python synapse_dataset_manager.py generate-template \
  --type Omic --format csv
```

A dataset workbook has an `Annotations` sheet with one column per schema attribute and
one editable row. Attribute descriptions are header comments. Enum values are stored
on a hidden `_lookups` sheet and referenced by Excel data validation, avoiding Excel's
255-character inline-list limit. Multi-value enum fields accept comma-separated values;
single-value enum fields reject values outside the dropdown.

`--format` accepts `json`, `csv`, or `xlsx`. When it is omitted, `.csv` and `.xlsx`
output suffixes infer the corresponding format; otherwise JSON is used.

## File templates: RecordSet and FileSet

```bash
# Generate per-file workbooks from a Synapse folder, routing each file explicitly
mamba run -n amp-als python synapse_dataset_manager.py generate-file-templates \
  --folder syn12345 --type Clinical --format xlsx \
  --file-tier-map annotations/file_tiers.json \
  --output annotations/clinical_file_templates.xlsx
```

`file_tiers.json` maps a Synapse entity ID (or filename) to its concrete tier:

```json
{
  "syn123": "recordset",
  "subject_001.csv": "fileset"
}
```

The workbook has one worksheet per concrete schema in the selected family, such as
`ClinicalRecordSetFile`, `ClinicalFileSetFile`, `OmicRecordSetFile`, and
`OmicFileSetFile`, including an empty tier sheet when no discovered rows are routed to
it. Each sheet includes `entityId`, `filename`, a hidden `_file_type`, and the
attributes for that concrete schema. Enum dropdowns are supplied from the hidden
`_lookups` sheet.

Use `--file-tier recordset` or `--file-tier fileset` when every discovered file belongs
to one tier. With the default `--file-tier both`, files not found in `--file-tier-map`
are emitted to an `Unassigned` sheet rather than guessed. Add them to the mapping and
regenerate. An exact concrete type such as `--type OmicRecordSetFile` routes all rows
to that schema.

For CSV file exports, one CSV is written per concrete schema, with names such as
`clinical_file_templates_ClinicalRecordSetFile.csv`; an additional `Unassigned.csv`
is written when necessary. CSV does not support Excel dropdowns.

## Current limitation

`apply-file-annotations` currently accepts the existing JSON template format. XLSX and
CSV exports are intended for editing and review; convert them to the JSON annotation
format before applying them to Synapse. The `entityId` and hidden `_file_type` columns
must be preserved for a future XLSX/CSV import workflow.

Enum values always come from `json-schemas/`, the generated data-model output. Rebuild
the relevant schemas before exporting after a data-model change.
