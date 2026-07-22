# XLSX Templates & Excel-based Annotation

## Overview

The `generate-template`, `generate-file-templates`, and `apply-file-annotations`
commands support **Excel (`.xlsx`) templates** in addition to JSON. This lets curators
fill in annotations in a spreadsheet where every field backed by an enum offers a
**dropdown of permissible values**, instead of hand-editing JSON.

Three capabilities were added:

1. **`--format xlsx`** on both template generators — emit a fill-in workbook instead of JSON.
2. **Dropdowns from the data model** — any attribute whose schema defines permissible
   values (an `enum`) gets an Excel data-validation dropdown listing those values.
3. **Blank templates with no Synapse folder** — `generate-file-templates` works without
   `--folder`, producing an empty attribute grid you fill row-by-row.
4. **xlsx input on apply** — `apply-file-annotations` accepts a filled-in `.xlsx` and
   applies it to Synapse exactly like the JSON path.

JSON remains the default for every command, so existing workflows are unchanged.

## How the xlsx is laid out

- **Columns** are the schema attributes for the chosen type.
- **`title`** is moved to the front to act as the leading index column.
- **Header cells** carry the attribute description as a cell comment (hover to read it).
- **Enum fields** show a dropdown when the cell is selected. Values live on a hidden
  `_lookups` sheet and are referenced by range, so large enums work (Excel's 255-char
  inline-list limit does not apply).
  - **Single-value** enum fields reject off-list entries.
  - **Multi-value** (array) enum fields offer the dropdown as a helper but also allow
    several **comma-separated** values in one cell.
- For per-file templates generated from a Synapse folder, two leading identifier columns
  are added — **`entityId`** and **`filename`** — plus a hidden-by-convention `_file_type`
  column so values round-trip back on apply. Keep `entityId` intact; it maps each row to a
  Synapse entity.

---

## Running it

All commands run through the `amp-als` env:

```bash
mamba activate amp-als
# or prefix each command with: mamba run -n amp-als ...
```

### 1. Dataset annotation template (xlsx)

```bash
python synapse_dataset_manager.py generate-template \
  --type Clinical \
  --format xlsx \
  --output annotations/clinical_dataset_template.xlsx
```

- `--type` — `Clinical`, `Omic`, or `Dataset` (default `Dataset`).
- `--format` — `json` (default) or `xlsx`. A `.xlsx` `--output` path also implies xlsx.
- `--output` — optional; defaults to `annotations/<type>_dataset_template.<ext>`.

### 2. Blank file template — no Synapse folder

Omit `--folder` to generate an empty fill-in grid without connecting to Synapse:

```bash
python synapse_dataset_manager.py generate-file-templates \
  --type Clinical \
  --format xlsx \
  --output annotations/blank_clinical_file_template.xlsx
```

The result is an empty sheet: columns are the file attributes, `title` is the leading
index column, enum columns have dropdowns, and validation extends down ~500 rows so you
can add one row per file. `--type` is `Clinical`, `Omic`, or `File` (default `File`).

JSON also works without a folder (drop `--format xlsx`), producing a single flat blank
template dict.

### 3. Per-file templates from a Synapse folder (xlsx)

When `--folder` **is** supplied, files are enumerated from Synapse and one row is
pre-populated per file (existing annotations included):

```bash
python synapse_dataset_manager.py generate-file-templates \
  --folder syn12345678 \
  --type Clinical \
  --format xlsx \
  --output annotations/my_dataset_file_templates.xlsx
```

All the existing flags (`--mapping`, `--metadata`, `--infer-variant-types`, etc.) still
apply; only the **output format** changes.

### 4. Apply a filled-in xlsx back to Synapse

`apply-file-annotations` detects `.xlsx`/`.xls` automatically:

```bash
# Dry run (default) — preview what would change
python synapse_dataset_manager.py apply-file-annotations \
  --annotations-file annotations/my_dataset_file_templates.xlsx

# Execute against Synapse
python synapse_dataset_manager.py apply-file-annotations \
  --annotations-file annotations/my_dataset_file_templates.xlsx \
  --execute
```

On load, each cell is coerced to its schema type (array fields split on commas, booleans
and numbers parsed, blanks dropped), rows are mapped to Synapse entities via `entityId`,
and the same validation + apply path as JSON runs.

---

## Arguments reference

| Command | Argument | Description |
|---------|----------|-------------|
| `generate-template` | `--format {json,xlsx}` / `-f` | Output format (default `json`) |
| `generate-template` | `--type {Clinical,Omic,Dataset}` | Dataset schema type |
| `generate-file-templates` | `--folder` | Synapse folder ID; **omit for a blank template** |
| `generate-file-templates` | `--format {json,xlsx}` / `-f` | Output format (default `json`) |
| `generate-file-templates` | `--type {Clinical,Omic,File}` | File schema type |
| `apply-file-annotations` | `--annotations-file` | `.json` **or** `.xlsx`/`.xls` |

---

## Notes & limitations

- **Multi-value cells**: Excel cannot natively multi-select from a dropdown. Enter several
  values comma-separated in one cell; they are split back into a list on apply.
- **Applying a blank template**: a blank file template contains attribute columns only. To
  apply it, add an `entityId` column with the target Synapse IDs (and optionally a
  `_file_type` column; it defaults to `File` when absent).
- **Source of truth**: enum values come from the generated JSON schemas in `json-schemas/`,
  which are built from `modules/**`. Rebuild the schemas after any data-model change so the
  dropdowns stay in sync.
</content>
</invoke>
