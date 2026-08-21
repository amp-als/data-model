# Quick Reference - New Features

## Setup

```bash
# IMPORTANT: Activate environment first
mamba activate amp-als
```

## 1. Generate Template

> `--type` is fuzzy-matched against `json-schemas/` — pass any schema (`clinical`, `omic`,
> `geo`, `sra`, `speech`, …) or an exact stem like `OmicDataset`. Not a fixed list.

```bash
# Generate empty dataset annotation template
python synapse_dataset_manager.py generate-template --type Clinical
python synapse_dataset_manager.py generate-template --type Omic -o my_template.json

# Excel template with enum dropdowns (see docs/XLSX_TEMPLATES.md)
python synapse_dataset_manager.py generate-template --type Clinical --format xlsx
# Blank file template (no Synapse folder needed)
python synapse_dataset_manager.py generate-file-templates --type Clinical --format xlsx
# Apply a filled-in .xlsx back to Synapse
python synapse_dataset_manager.py apply-file-annotations --annotations-file filled.xlsx --execute
```

## 2. Link Dataset (No Files)

```bash
# Step 1: Generate template
python synapse_dataset_manager.py create --dataset-name "My Link Dataset" --link-dataset

# Step 2: Edit annotations/My_Link_Dataset_dataset_annotations.json
# Add: "url": "https://example.com/external-data"

# Step 3: Create dataset
python synapse_dataset_manager.py create \
  --dataset-name "My Link Dataset" \
  --link-dataset \
  --from-annotations \
  --execute
```

### Config-based:

```yaml
# config.yaml
datasets:
  MY_LINK_DATASET:
    dataset_name: "External GEO Dataset"
    dataset_type: "Omic"
    link_dataset: true
```

```bash
python synapse_dataset_manager.py create --use-config MY_LINK_DATASET
# Edit annotations, add url field
python synapse_dataset_manager.py create --use-config MY_LINK_DATASET --from-annotations --execute
```

## 3. Add Link File (External URL Reference)

```bash
# Basic usage (creates in project)
python synapse_dataset_manager.py add-link-file \
  --name "GEO Dataset" \
  --url "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE12345" \
  --execute

# Add to specific dataset
python synapse_dataset_manager.py add-link-file \
  --name "External RNA-seq Data" \
  --url "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE12345" \
  --dataset-id syn67890 \
  --execute

# With annotations
python synapse_dataset_manager.py add-link-file \
  --name "Proteomics Data" \
  --url "https://example.com/data.zip" \
  --dataset-id syn67890 \
  --annotations '{"dataType": "proteomics", "platform": "Olink"}' \
  --execute
```

## Python Code Snippets

### Add File to Dataset

```python
from synapseclient import Dataset
from synapseclient.models import File

dataset = Dataset("syn12345").get()
file_ref = File(id="syn67890")
dataset.add_item(file_ref)
dataset.store()
```

### Create Link File

```python
from synapseclient.models import File
import tempfile, os

temp = tempfile.NamedTemporaryFile(mode='w', delete=False)
temp.write("placeholder")
temp.close()

try:
    link = File(
        parent_id="syn12345",
        name="External Link",
        path=temp.name,
        external_url="https://example.com/data",
        synapse_store=False
    ).store()
finally:
    os.unlink(temp.name)
```

## 4. Reorder Dataset Columns

```bash
# Dry run (default) — auto-detects dataset type from annotations
python synapse_dataset_manager.py reorder-columns --dataset-id syn12345

# Explicit dataset type
python synapse_dataset_manager.py reorder-columns --dataset-id syn12345 --dataset-type OmicDataset

# Execute
python synapse_dataset_manager.py reorder-columns --dataset-id syn12345 --dataset-type OmicDataset --execute

# Port the exact columns + order from another dataset/view instead of a schema
python synapse_dataset_manager.py reorder-columns --dataset-id syn12345 --from-entity syn67890 --execute
```

This adds any missing columns, reorders them per the priority template, and verifies the final layout. If `--dataset-type` is omitted, it auto-detects from the dataset's annotations. A Synapse Dataset's table shows one row per included **file**, so columns (name, Synapse type, facet, size constraints) are derived from the matching **File**-type schema's `json-schemas/` properties (e.g. `--dataset-type speech` → `SpeechFile`, not `SpeechDataset`) — not a hand-maintained list — so every modeled field is available and correctly typed automatically. Add `--columns field1 field2 ...` to cherry-pick/order specific fields instead of adding every property on the schema; a name not found in the schema still gets added as a generic faceted STRING column rather than being dropped. `--from-entity <syn_id>` ports the exact columns and current order from any existing entity that has columns (Dataset, EntityView, or Table) instead of deriving from a schema at all — combine with `--columns` to port only specific names (source order preserved).

## 5. Create Entity View (standalone folder)

```bash
# Dry run (default) — generic File columns
python synapse_dataset_manager.py create-entity-view --folder syn76934900

# Type-aware columns (fuzzy-matched against json-schemas/, e.g. "omic" -> OmicFile)
python synapse_dataset_manager.py create-entity-view --folder syn76934900 --type omic --name "ASSESS Raw Files"

# Cherry-pick specific columns instead of every property on the schema
python synapse_dataset_manager.py create-entity-view --folder syn76934900 --type omic --columns assay platform libraryStrategy

# Combine multiple schemas into one view — pass several --type values (any exact
# schema name works too, not just File/Dataset pairs, e.g. "MetadataSchema")
python synapse_dataset_manager.py create-entity-view --folder syn76934900 --type speech MetadataSchema --columns schemaName attributes recordingDevice

# Port the exact columns + order from an existing Dataset/EntityView/Table instead of
# deriving them from a schema at all — ignores --type/--extra-schema-types
python synapse_dataset_manager.py create-entity-view --folder syn76934900 --from-entity syn72016774 --name "New View"

# --columns filters a --from-entity port down to just those names (source order kept)
python synapse_dataset_manager.py create-entity-view --folder syn76934900 --from-entity syn72016774 --columns dataType fileFormat species

# Execute (creates the view, reorders + verifies columns)
python synapse_dataset_manager.py create-entity-view --folder syn76934900 --type omic --name "ASSESS Raw Files" --execute
```

Creates a standalone Synapse entity view (table) scoped to any folder ID — no dataset entity required. `--project-id` defaults to `config.yaml`'s `project_id` if omitted; `--name` defaults to the folder's Synapse ID (`_EntityView` is appended). Since entity views scope Files/Folders, columns are pulled from the matching **File**-type schema's properties (e.g. `--type omic` → `OmicFile`) — every property by default, or just the names passed to `--columns` (each still gets its real type/facet from the schema when it matches a modeled field). `--type` accepts multiple values — pass several to merge properties from more than one schema into a single view (any exact schema name works, including non-File/Dataset schemas like `MetadataSchema`; later schemas win on name clashes). `--from-entity <syn_id>` ports the exact columns (name, type, facet, size constraints) and current order from any existing entity that has columns (Dataset, EntityView, or Table), skipping schema derivation entirely — add `--columns` alongside it to port only specific names (source order preserved, not the order given). Add `--skip-reorder` to skip the post-creation column reorder/verify steps. For a view scoped to a *dataset* created via the `create` workflow, that path is wired to run automatically right after dataset creation (default on, disable with `--skip-entity-view`) — see §9.

## 6. Rename Files (no re-upload)

```bash
# Single file — renames display name AND download filename
python synapse_dataset_manager.py rename-files --file-id syn12345 --new-name "sample_01.fastq.gz" --execute

# Batch from a mapping file (JSON {synId: newName}, or CSV/XLSX)
python synapse_dataset_manager.py rename-files --mapping-file renames.json --execute

# Find/replace across a dataset (add --regex to treat --find as a regex)
python synapse_dataset_manager.py rename-files --dataset-id syn67890 --find "raw_" --replace "" --execute

# Across a whole collection
python synapse_dataset_manager.py rename-files --collection-id syn66496326 --regex --find "^GSE[0-9]+_" --replace "" --execute
```

Renames the entity name and the download filename **without re-uploading data** (server-side file-handle copy). Add `--name-only` to change just the display name, `--new-version` to force a version bump. Dry-run by default. See [RENAME_FILES.md](RENAME_FILES.md) for full details.

## 7. Field Migrations (reconcile renamed/removed slots)

When the data model changes but Synapse still holds the old annotations, the
`update` workflow reconciles them using `configs/field_migrations.yaml`. Applied
automatically during phase-1 template generation — no flag needed.

```yaml
# configs/field_migrations.yaml — one entry per deprecated field
source:                       # rename + translate enum values
  target: originalRepository
  values: {all_als: Synapse}
individualCount:              # plain rename (value carried as-is)
  target: participant_count
collection:                   # removed from the model
  drop: true
hasLongitudinalData:          # in-place type/shape fix: [False] -> False
  type: boolean
```

```bash
# Uses configs/field_migrations.yaml by default; override with a flag:
python synapse_dataset_manager.py update --dataset-id syn123 --staging-folder syn456 \
  --field-migrations path/to/custom_migrations.yaml
```

Add an entry **every time you rename or remove a slot** in `modules/**`. Canonical
field wins on rename; unmapped `values:` are dropped so nothing invalid leaks into
enum fields; `type:` coerces shape (scalar unwraps `[x]`→`x`, `array` wraps). See
[NEW_FEATURES_DOCUMENTATION.md](NEW_FEATURES_DOCUMENTATION.md) for the full spec.

## 8. Move Files (bulk move, optional pattern filter)

```bash
# Move every file directly in syn111 into syn222 (subfolders of syn111 untouched)
python synapse_dataset_manager.py move --source syn111 --target syn222 --execute

# Only move CSVs sitting in the root of syn111 (its subfolders are not descended into,
# so anything already inside syn222 or other child folders is left alone)
python synapse_dataset_manager.py move --source syn111 --target syn222 --pattern "*.csv" --execute

# Same, but also pull matching files out of subfolders of syn111
python synapse_dataset_manager.py move --source syn111 --target syn222 --pattern "*.csv" --recursive --execute
```

`--source` accepts one or more file and/or folder Synapse IDs; folder sources expand to
their contained files. `--pattern` (fnmatch glob, e.g. `*.csv`) filters files discovered
by expanding a folder/project source — files passed explicitly by ID in `--source` are
always moved regardless of pattern. `--recursive` controls whether subfolders of a folder
source are descended into (pattern filtering applies at every level reached). Files
already in the target folder are automatically skipped. Dry-run by default; add `--execute`
to actually move files.

## 9. Create Dataset — Type, Entity View, and Multi-Schema Columns

```bash
# Explicit dataset type — fuzzy-matched against json-schemas/ (e.g. "speech" -> SpeechDataset).
# Overrides config/name-pattern detection. Without it, type is auto-detected from
# config.yaml's dataset_type, then name-pattern matching (omic/clinical/speech/geo/sra
# keywords), then defaults to the generic Dataset schema.
python synapse_dataset_manager.py create --staging-folder syn111 --dataset-name "My Speech Study" --dataset-type speech

# --dataset-type also works with --from-annotations, overriding whatever _dataset_type
# Phase 1 already saved in <name>_dataset_annotations.json
python synapse_dataset_manager.py create --dataset-name "My Speech Study" --dataset-type speech --from-annotations --execute

# Entity view (staging-folder validation view, STEP 3) is created by DEFAULT — disable with:
python synapse_dataset_manager.py create --dataset-name "My Study" --from-annotations --skip-entity-view --execute
# ...or in config.yaml: create_entity_view: false

# Cherry-pick/order specific columns instead of every property on the resolved schema(s) —
# applies to BOTH the validation entity view and the dataset table columns
python synapse_dataset_manager.py create --dataset-name "My Study" --from-annotations \
  --columns title schemaName recordingDevice --execute

# Merge in additional schemas (any exact schema name, not just File/Dataset pairs) for
# BOTH the validation entity view and the dataset table columns
python synapse_dataset_manager.py create --dataset-name "My Study" --from-annotations \
  --extra-schema-types MetadataSchema --execute

# Port the exact columns + order from an existing entity for BOTH steps, instead of
# deriving from a schema at all — ignores --extra-schema-types
python synapse_dataset_manager.py create --dataset-name "My Study" --from-annotations \
  --from-entity syn67890 --execute
```

`--columns`/`--extra-schema-types`/`--from-entity` are also settable per-dataset in `config.yaml`
(`columns:`, `extra_schema_types:`, `from_entity:`) — CLI flags win over config. A `--columns`
name not found in any resolved schema still gets added as a generic faceted STRING column
rather than being dropped. `--from-entity` combined with `--columns` filters the ported set
down to just those names (source order preserved).

Both the validation entity view **and** the dataset table columns pull from the **File**-type
schema (e.g. `--dataset-type speech` → `SpeechFile`, not `SpeechDataset`) — a Synapse Dataset's
own table shows one row per included file, so its columns need to be file-level annotation
fields to mean anything. `--extra-schema-types` values are used as given (no File/Dataset
conversion), so a non-File/Dataset schema like `MetadataSchema` merges in unchanged for both.

## Help Commands

```bash
# Main help
python synapse_dataset_manager.py --help

# Command-specific help
python synapse_dataset_manager.py generate-template --help
python synapse_dataset_manager.py add-link-file --help
python synapse_dataset_manager.py create --help
python synapse_dataset_manager.py create-entity-view --help
python synapse_dataset_manager.py move --help
```
