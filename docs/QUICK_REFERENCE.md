# Quick Reference - New Features

## Setup

```bash
# IMPORTANT: Activate environment first
mamba activate amp-als
```

AI-assisted annotations are disabled by default. To explicitly enable them, set
`USE_AI=true` or `ai.enabled: true` in `config.yaml`.

## 1. Generate Template

> `--type` is fuzzy-matched against `json-schemas/` — pass any schema (`clinical`, `omic`,
> `geo`, `sra`, `speech`, …) or an exact stem like `OmicDataset`. Not a fixed list.

```bash
# Generate empty dataset annotation template
python synapse_dataset_manager.py generate-template --type Clinical
python synapse_dataset_manager.py generate-template --type Omic -o my_template.json

# Excel template with enum dropdowns (see docs/XLSX_TEMPLATES.md)
python synapse_dataset_manager.py generate-template --type Clinical --format xlsx
# CSV template (CSV has no dropdown support)
python synapse_dataset_manager.py generate-template --type Omic --format csv
# Per-file RecordSet/FileSet workbook; route mixed folders with a tier map
python synapse_dataset_manager.py generate-file-templates --folder syn12345 --type Clinical \
  --format xlsx --file-tier-map annotations/file_tiers.json
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

# Directly merge BiomarkerFile columns with MetadataSchema columns
python synapse_dataset_manager.py reorder-columns --dataset-id syn12345 \
  --dataset-type biomarker --extra-schema-types MetadataSchema --execute

# Replace an old Dataset column layout with exactly the merged schema columns.
# Dry-run first (omit --execute), then execute after reviewing the removal list.
python synapse_dataset_manager.py reorder-columns --dataset-id syn12345 \
  --dataset-type biomarker --extra-schema-types MetadataSchema \
  --replace-columns --execute
```

This adds any missing columns, reorders them per the priority template, and verifies the final layout. `--extra-schema-types` merges one or more additional exact schema names; for example, `--dataset-type biomarker --extra-schema-types MetadataSchema` merges `BiomarkerFile` with `MetadataSchema` directly on the Dataset, without an intermediary entity view. `--replace-columns` is destructive: it removes all existing non-system Dataset columns and recreates only the resolved/merged schema columns, while preserving the Dataset, its member files, their annotations, and Synapse system columns. It is still a dry-run unless `--execute` is supplied. If `--dataset-type` is omitted, it auto-detects from the dataset's annotations. A Synapse Dataset's table shows one row per included **file**, so columns (name, Synapse type, facet, size constraints) are derived from the matching **File**-type schema's `json-schemas/` properties (e.g. `--dataset-type speech` → `SpeechFile`, not `SpeechDataset`) — not a hand-maintained list — so every modeled field is available and correctly typed automatically. Add `--columns field1 field2 ...` to cherry-pick/order specific fields instead of adding every property on the schema; a name not found in the schema still gets added as a generic faceted STRING column rather than being dropped. `--from-entity <syn_id>` ports the exact columns and current order from any existing entity that has columns (Dataset, EntityView, or Table) instead of deriving from a schema at all — combine with `--columns` to port only specific names (source order preserved).

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
originalRepository:           # plain rename (value carried as-is)
  target: repository
source:                       # route legacy source values by meaning
  routes:
    - when_values: [geo, GEO]
      target: repository
      values: {geo: Gene Expression Omnibus, GEO: Gene Expression Omnibus}
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

## 9. Delete Entities (bulk, recursive)

```bash
# Preview deleting two files (dry-run by default — nothing is deleted)
python synapse_dataset_manager.py delete-entities --syn-id syn111 syn222

# Delete an empty folder
python synapse_dataset_manager.py delete-entities --syn-id syn333 --execute

# Delete a folder (or project) that has files/subfolders inside it — --recursive
# is required or the target is refused and skipped
python synapse_dataset_manager.py delete-entities --syn-id syn444 --recursive --execute
```

`--syn-id` accepts one or more Synapse IDs (files, folders, and/or projects) for bulk
deletion in a single call. Deleting a Folder/Project on Synapse cascades to all of its
descendants server-side, so `--recursive` is a client-side safety gate: a container that
has any children is refused (with a descendant count reported) unless `--recursive` is
passed — it does not change how the deletion itself happens. Dry-run by default; add
`--execute` to actually delete, which additionally requires typing `DELETE` at a
confirmation prompt before anything is removed. Use `--verbose` to list every descendant
discovered while walking a folder/project.

## 10. Create Dataset — Type, Entity View, and Multi-Schema Columns

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

## 11. Generate a Mapping from a SomaLogic ADAT File

```bash
python synapse_dataset_manager.py generate-mapping \
  --input /data/study.soma.adat \
  --output mapping/somalogic.dict
```

`generate-mapping` reads `.adat` files with `somadata.read_adat()` (install with
`pip install somadata`). It scaffolds fields from all ADAT metadata sections, but not
RFU matrix values: `header__*` fields are study-level metadata, `sample__*` fields are
sample metadata, and `protein__*` fields are SOMAmer/analyte annotations. The prefixes
avoid collisions between the sections. ADAT files are also accepted by
`generate-file-templates --metadata`; use `sample__*` fields for sample/file mappings.

## 12. Create Dataset with Mapping Generation or Application

The `create` phase-1 workflow can optionally generate and/or apply a file-annotation
mapping. With `--metadata`, it uses those CSV/XLSX/ADAT files. Without metadata, it
downloads each supported file in the staging folder and builds a mapping scaffold from
CSV/Excel columns or ADAT header, sample-index, and protein-column metadata. Raw ADAT
expression-matrix values are deliberately ignored.

```bash
# Generate a scaffold from every supported staging file (CSV/XLSX/ADAT)
python synapse_dataset_manager.py create \
  --staging-folder syn123456 \
  --dataset-name "My Biomarker Study" \
  --dataset-type biomarker \
  --generate-mapping mapping/my_biomarker.dict

# Edit target fields/value translations in the generated mapping, then regenerate
# file annotations using each file's own tabular/ADAT metadata.
python synapse_dataset_manager.py create \
  --staging-folder syn123456 \
  --dataset-name "My Biomarker Study" \
  --dataset-type biomarker \
  --mapping mapping/my_biomarker.dict

# Equivalent when retaining a workflow command/config that includes
# --generate-mapping: use that existing mapping without merging a new scaffold.
python synapse_dataset_manager.py create \
  --staging-folder syn123456 \
  --dataset-name "My Biomarker Study" \
  --dataset-type biomarker \
  --generate-mapping mapping/my_biomarker.dict \
  --skip-mapping-generation

# Generate a scaffold from one or more external metadata files instead.
python synapse_dataset_manager.py create \
  --staging-folder syn123456 \
  --dataset-name "My Biomarker Study" \
  --dataset-type biomarker \
  --metadata metadata/study.xlsx metadata/assays.adat \
  --generate-mapping mapping/my_biomarker.dict
```

`--generate-mapping` safely merges newly discovered columns/values into an existing
mapping and never replaces completed mappings. A new scaffold has empty targets, so it
must be reviewed before it can populate annotations. Its `_views` entries are applied as
file-level annotations after field mappings; the view is inferred from mapped file columns
when possible, otherwise the staging filename stem is used. `--mapping` alone always skips
mapping generation; `--skip-mapping-generation` does the same when retaining a
`--generate-mapping` argument. Use `--mapping-source files` to inspect staging files even
when `--metadata` is supplied, or `--mapping-source metadata`
to require external metadata. `--mapping-max-values` controls the per-field value-map
limit (default: 50). Unsupported or unreadable staging files retain normal templates and
are reported, rather than failing creation.

## 13. Retain the Old Annotation During a Rename

Use `--keep-old-annotation` to copy values to the canonical field while retaining
the deprecated field for a staged migration. Dry-run first, then add `--execute`.

```bash
mamba run -n amp-als python synapse_dataset_manager.py rename-annotation \
  --collection-id syn66496326 \
  --old-annotation source --new-annotation repository \
  --include-files --inherit-dataset-annotation --keep-old-annotation --execute
```

Without `--keep-old-annotation`, `rename-annotation` removes the old key after a
successful copy. A blank target value (such as `repository: [""]`) is treated as
empty and is overwritten from the old key without a conflict prompt. If both keys
already have matching values, the flag leaves both unchanged; conflicting populated
values still require an interactive choice during execution. Add
`--inherit-dataset-annotation` to make member files that have neither populated key
inherit the Dataset's populated canonical value. Inheritance is opt-in because fields
such as participant counts can legitimately differ between a Dataset and its files.

## 14. Sync Dataset Schema Annotations

Validate dataset-level annotations in a DatasetCollection and generate templates before applying a reviewed delta file. Dataset type detection recognizes speech and biomarker datasets from their existing `dataType` values, in addition to clinical and omic metadata.

```bash
# Generate Synapse-backed validation reports and merged templates; dry-run is the default.
mamba run -n amp-als python synapse_dataset_manager.py sync-dataset-schema-annotations \
  --collection-id syn66496326 \
  --template-mode merged \
  --output-dir annotations/data_category_sync \
  --dry-run

# Preview a reviewed, approved delta file, then add --execute to apply it.
mamba run -n amp-als python synapse_dataset_manager.py sync-dataset-schema-annotations \
  --collection-id syn66496326 \
  --updates-file annotations/data_category_sync/proposed_deltas.json \
  --require-approved \
  --dry-run
```

`--updates-file` must name a JSON file, while `--output-dir` names the report/template directory. See [SCHEMA_ANNOTATION_SYNC_WORKFLOW.md](SCHEMA_ANNOTATION_SYNC_WORKFLOW.md) for the full review-and-apply workflow.

## 15. Generate Mixed-Schema File Templates

Use `--file-type-map` when a folder contains files requiring different schemas.
The argument accepts a JSON file path or an inline JSON object. Map by Synapse ID
(preferred) or filename; an ID assignment wins when both are present. The map's
values must be exact schema names. Mixed-schema templates support JSON output
only and do not contain one top-level `$schema`; each entry's `_file_type` is
used for validation by `apply-file-annotations`.

```json
{
  "syn78079710": "BiomarkerFile",
  "syn77160042": "MetadataSchema",
  "README.md": "MetadataSchema"
}
```

```bash
mamba run -n amp-als python synapse_dataset_manager.py generate-file-templates \
  --folder syn78362817 \
  --file-type-map annotations/abbvie/olink_file_types.json \
  --output annotations/abbvie/ALSKP_Olink_v03_file_annotations.json \
  --skip-ai --refresh-walkthrough
```

Use `--type BiomarkerFile` alongside the map only to provide a fallback for
unmapped files. Without `--type`, unmapped files use normal filename detection.

## 16. Package Entry Point

From the data-model repository root, the package entry point supports the same
commands and flags as the original script:

```bash
mamba run -n amp-als python -m synapse_dataset_manager --help
mamba run -n amp-als python -m synapse_dataset_manager update --help
```

`python synapse_dataset_manager.py ...` remains supported as a compatibility
wrapper. The implementation now lives in `synapse_dataset_manager/cli.py`.
Working-directory-relative config, schema, mapping, and output paths are unchanged;
use `-c configs/config.yaml` before the subcommand to select that config explicitly.
The package also provides explicit update policies; see section 17 below.
See [the packaging and update redesign plan](DATASET_MANAGER_REFACTOR_PLAN.md)
for the staged implementation and future repository extraction.

## 17. General and Custom Update Policies

`update` now defaults to `general`: exact filenames or explicit target IDs, no
fuzzy/form/view matching, and no implicit content downloads or first-file metadata
inheritance. Existing dataset members missing from staging remain unchanged.
Ambiguous matches, duplicate targets, and duplicate new filenames are errors.

```bash
# Generic preparation using a file identity manifest
mamba run -n amp-als python -m synapse_dataset_manager -c configs/config.yaml update \
  --dataset-id syn123 --staging-folder syn456 \
  --identity-manifest metadata/file_identity.csv \
  --data-dict metadata/dictionary.csv \
  --dictionary-group-column table_id --dictionary-field-column variable_name

# Alternatively, derive release names from one column in each incoming file
mamba run -n amp-als python -m synapse_dataset_manager update \
  --dataset-id syn123 --staging-folder syn456 --name-column instrument_name

# ALL ALS must now be selected explicitly
mamba run -n amp-als python -m synapse_dataset_manager -c configs/config.yaml update \
  --use-config ALL_ALS_ASSESS --workflow all_als
```

Identity manifests are CSV files, separate from annotation-value `.dict` mappings:

```csv
source_filename,release_filename,target_synapse_id,dictionary_group
export_001.csv,participants.csv,syn111,participants
export_002.csv,visits.csv,,visits
```

Use `source_synapse_id` instead of (or consistently with) `source_filename` when
filenames are ambiguous. Unlisted sources retain their names. A missing target ID
uses normal matching before proposing an addition. An explicit target must already
belong to the dataset. Existing entities keep their filenames; manifest release
names affect matching and naming additions, not implicit renames.

`--name-column` and `--identity-manifest` are mutually exclusive. Name extraction
requires one distinct nonempty value per file and retains its extension. Missing
columns or multiple values fail preparation. Only this option downloads general
workflow files for name extraction (supported by the existing tabular loader).

Generic dictionaries use one field per row. `--dictionary-field-column` defaults
to `Field`; `--dictionary-description-column` defaults to `Description`.
`--dictionary-group-column` is optional; without it the dictionary is ungrouped.
Groups must be populated on every row; no implicit forward-fill occurs.
Conflicting repeated field definitions fail rather than silently overwrite.
The generated mapping uses `_groups` for editable group-level annotations, keyed
by exact group name. Manifest `dictionary_group` selects these annotations;
existing nonempty values are preserved. Group association does not create a
`viewName` annotation. Field/value mappings still use the existing global mapping
format; group-specific conflicting field definitions and coded-value dictionary
layouts are not yet supported by the generic parser.

All new options can also be set under a dataset's `update` section using snake_case
keys (`workflow`, `identity_manifest`, `name_column`, `dictionary_group_column`,
`dictionary_field_column`, `dictionary_description_column`). CLI values override
configuration. Workflow modules live in
`synapse_dataset_manager/updates/workflows/` and are explicitly registered there;
input files cannot select arbitrary Python paths.

Phase 1 writes separate file and Dataset annotations JSON files. Pass both
`--annotations-file` and `--dataset-annotations-file` in Phase 2 to include the
Dataset entity update as an `annotate_dataset` action in the same reviewed plan as
file updates. For ALL ALS, Phase 1 sets the Dataset-level `participant_count`
from the one staged demographics (`*DEMOG`) file using its `NeuroGUID` column,
falling back to common identifiers such as `SubjectID` when needed; it does not
set a Dataset-level `recordCount` or sum counts across files. Multiple
staged demographics files fail rather than choosing one; no staged demographics
file leaves the existing Dataset participant count unchanged. Review the Dataset
entry like any other action; it does not alter Dataset membership or apply a file
version label. Phase 2 defaults to a dry run and requires
`--execute` for writes. Staging and local uploads cannot be combined; additions
require a release folder before execution begins. Operation/verification failures
now produce a failure exit status, not a success banner. This is not transactional:
inspect partial results before retrying. Execution now requires a reviewed plan;
see section 18 and [Reviewed Update Plans](REVIEWED_UPDATE_PLANS.md).

To apply only a reviewed Dataset annotation artifact—without file update actions—use
the dedicated command. It accepts the Phase-1 Dataset wrapper directly:

```bash
mamba run -n amp-als python -m synapse_dataset_manager annotate-dataset \
  --dataset-id syn123 \
  --annotations-file "annotations/Example_dataset_update_annotations.json" \
  --execute
```

## File rebuild manifest generation

Generate a metadata-only draft from explicit staging folders and an exact source filename:

```bash
mamba run -n amp-als python -m synapse_dataset_manager generate-file-rebuild-manifest \
  --source-file synOLD --source-filename raw.csv --output-folder synOUTPUT \
  --staging-folder v1=synSTAGING1 v2=synSTAGING2 --output rebuild.json
```

The order of the labeled folders determines version order. Missing filenames prompt
for an alternative; `--non-interactive` fails instead. Review the draft before
running `rebuild-file-entity`. See [File and Dataset rebuild notes](REBUILD_FILE_AND_DATASET_ENTITIES.md).

## Dataset rebuild manifest generation

Create a metadata-only draft from completed File rebuild output:

```bash
mamba run -n amp-als python -m synapse_dataset_manager generate-dataset-rebuild-manifest \
  --source-dataset synDATASET --file-rebuild-report file_rebuild_result.json \
  --output-name 'Corrected Dataset' --output dataset_rebuild.json
```

To generate only reviewed source snapshots, repeat `--source-version` with positive
Dataset version numbers. Omit the flag to include all snapshots. Missing requested
versions fail before snapshot membership is read; selected releases are emitted in
source-version order. For example:

```bash
mamba run -n amp-als python -m synapse_dataset_manager generate-dataset-rebuild-manifest \
  --source-dataset syn123 --source-version 1 --source-version 3 \
  --replace-member 1:syn111=syn222:2 --replace-member 3:syn111=syn222:3 \
  --output-name 'Corrected Dataset' --output dataset_rebuild.json --non-interactive
```

Explicit replacements must refer to members in selected snapshots; unselected
snapshots do not need mappings and are not included as releases. The draft records a
baseline of **all** source snapshots (membership, labels, comments and annotations),
including unselected ones. Generation fails if the source version list changes during
baseline capture; retry and review the new draft. Execution rejects missing or changed
baselines; regenerate and review if history changes. Reading all snapshot metadata is
required even for a subset.

Repeat `--replacement-folder synFOLDER` and/or `--replacement-file synFILE`
to collect candidates from multiple sources, optionally together with `--file-rebuild-report`.
Report and exact-name/label candidates are combined and deduplicated before review:

```bash
mamba run -n amp-als python -m synapse_dataset_manager generate-dataset-rebuild-manifest \
  --source-dataset syn123 --replacement-folder syn456 --replacement-folder syn789 \
  --replacement-file syn999 --output-name 'Corrected Dataset' --output draft.json
```

Matching uses exact File names and version labels. Every folder/File candidate requires
interactive review, even a single match; dates and comments are shown as evidence, not
assumed equal. Missing names (including renamed Files) and missing or ambiguous versions
prompt for an explicit choice; `--non-interactive` fails instead. Report candidates also
require review; use explicit `--replace-member` mappings for non-interactive selection. A missing name can only be explicitly kept or aborted; to map a renamed
File, use a reviewed File rebuild report or explicit mapping. Explicit keeps are recorded in `kept_members`.
Review all choices and retained IDs.

For an unavailable (including trashed) original, supply a reviewed mapping per source
snapshot, without fetching the old File. For example, explicit mappings can be used
alone or alongside a report or folder; they take precedence for those members:

```bash
mamba run -n amp-als python -m synapse_dataset_manager generate-dataset-rebuild-manifest \
  --source-dataset syn123 --replace-member 1:syn111=syn222:2 \
  --replace-member 2:syn111=syn222:3 --output-name 'Corrected Dataset' \
  --output dataset_rebuild.json --non-interactive
```

The syntax is `SOURCE_DATASET_VERSION:synOLD=synNEW:REPLACEMENT_VERSION`;
both versions must be positive integers. Each old ID must occur in that snapshot;
replacement IDs must not collide with retained or other replacement members. The
replacement version is checked as a File using metadata only. Unmapped members retain
their pinned references when no report or folder is supplied. Explicit removals and
reviewed `member_additions` remain available; review and preview the draft.

Preview a reviewed manifest:

```bash
mamba run -n amp-als python -m synapse_dataset_manager rebuild-dataset-entity \
  --manifest dataset_rebuild.json --output dataset_rebuild_plan.json
```

To explicitly omit an obsolete File from snapshots, repeat `--exclude-member synOLD`
when generating the manifest; this records `member_removals` for affected releases
without fetching that File. Preview validates that each removed member was present.

To add a pinned File absent from a source snapshot, put
`"member_additions": [{"id": "synFILE", "version": 2}]` in that release entry.
Duplicate and unpinned additions fail validation.

The preview reads metadata only, validates all retained, replacement and added pinned
File versions and version-specific annotations, and infers the output Project. After reviewing it, explicitly execute:

```bash
mamba run -n amp-als python -m synapse_dataset_manager rebuild-dataset-entity \
  --manifest dataset_rebuild.json --output dataset_rebuild_result.json --execute
```

Execution copies the latest wiki hierarchy and markdown and reports Synapse IDs found
in page text without rewriting links. Wiki attachments are not copied: execution warns
and records their source IDs and names in the report for manual reattachment. Links to
attachments in copied markdown may not work until repaired. Wiki markdown is downloaded
only during execution. Each snapshot and copied wiki page is verified. The required
output records partial progress and failure phase; rebuild manifest generation, File and
Dataset previews, and execution refuse existing output files. Use separate new paths for
drafts, plans and reports. File and Dataset execution reserve their report path exclusively
before downloads or remote writes and flush progress updates; competing executions using
the same path fail. Do not delete or replace a reserved report while execution is running.
The latest source Dataset description is copied at creation. A timeout can leave an unknown
server-side outcome: inspect Synapse and the report manually before retrying; never
blindly rerun. This path has not yet been validated in an authenticated sandbox.

## 18. Review an Update Plan Before Execution

After editing the generated annotations, create a read-only preview and plan:

```bash
mamba run -n amp-als python -m synapse_dataset_manager update \
  --dataset-id syn123 --annotations-file annotations/Example_update_annotations.json \
  --release-folder syn789 --version-label v2 \
  --write-plan annotations/Example_v2.plan.json

# Review the plan AND annotation values, then apply the same inputs/options:
mamba run -n amp-als python -m synapse_dataset_manager update \
  --dataset-id syn123 --annotations-file annotations/Example_update_annotations.json \
  --release-folder syn789 --version-label v2 \
  --plan-file annotations/Example_v2.plan.json --execute
```

`--write-plan` is dry-run only, refuses overwrite, and defaults to the annotations
path with a `.plan.json` suffix. `--plan-file` validates a reviewed plan; without
`--execute` it only checks/previews it. **Execution requires `--plan-file`.**
Annotations, options, membership, entity snapshots, and local bytes must still
match the reviewed state; `--skip-validation` does not bypass these checks.
Legacy annotation files work through the dry-run planning step, not direct apply.

Execution stops on failure and records partial progress in
`<plan-file>.results.json`. Inspect it before recovery and generate a fresh plan;
a plan with an existing execution report cannot be replayed. Versioned files now
refresh the dataset's pinned version references. See
[Reviewed Update Plans](REVIEWED_UPDATE_PLANS.md) for stale checks, verification,
recovery, and concurrency limitations.

## 19. ALL ALS Dictionary, Required-Header, and PHI/PII Gate

ALL ALS phase 1 requires `--workflow all_als` and a data dictionary. Before it
writes annotations or a plan, every staged CSV/XLS/XLSX file is checked against
the dictionary view named by its raw staging filename (without its extension).
The dictionary supports sparse `View Name` cells and fully populated view rows.

To run the gate and save a shareable, value-free Markdown report, use phase 1
without `--execute`:

```bash
mamba run -n amp-als python -m synapse_dataset_manager -c configs/config.yaml update \
  --use-config ALL_ALS_ASSESS --workflow all_als \
  --preflight-report annotations/all_als_preflight_report.md
```

The report is written for both pass and fail outcomes. By default it contains only
filenames, views, columns, finding counts, and row numbers; it never includes
source cell values. `--preflight-report` is local-only and applies to ALL ALS
phase 1.

If the report is being handled as restricted PHI, `--include-violation-values`
adds every detected raw date value to terminal failures and the Markdown report:

```bash
mamba run -n amp-als python -m synapse_dataset_manager -c configs/config.yaml update \
  --use-config ALL_ALS_ASSESS --workflow all_als \
  --preflight-report annotations/restricted_all_als_preflight.md \
  --include-violation-values
```

Do **not** use that flag for reports that will be shared outside the approved PHI
handling environment.

A first `(View Name, Field)` row defines a column; later contiguous rows repeating
that `Field` define permissible `Values` codes and their `Description` labels. A
first-row `Values` value of empty or `NA` is the default definition marker; `NA`
on a repeated row is retained as a permissible value code. Multiple `NA` rows with
distinct descriptions are retained as ambiguous metadata and excluded from
automatic value mapping; an identical repeated code/description is deduplicated
and printed as a dictionary warning. Substantive file headers and that view's unique dictionary fields must match exactly
after case/space/hyphen/underscore normalization.

```yaml
# Dataset entry in config.yaml
ALL_ALS_ASSESS:
  data_dict: metadata/all_als_dictionary.csv
  update:
    workflow: all_als
    all_als:
      allow_leading_empty_index: true  # One unnamed first row-index column is allowed
      dictionary:
        view_column: "View Name"
        field_column: "Field"
        description_column: "Description"
        value_column: "Values"
        definition_value_markers: ["", "NA"]
        ignored_file_columns: ["Form Name", "NeuroGUID", "NeuroSTAmP", "visit_name"]
      # Legacy dictionary-only fields: warn if defined, but do not require in files.
      dictionary_exceptions: ["localUID", "subjectUID", "siteUID", "initials",
                              "reason_for_failure", "state", "visit"]
      required_columns:
        all_files: ["NeuroGUID", "NeuroSTAmP"]
        by_view:
          v_ALLALS_AS_ASSEDEMOG: ["nihguid"]
      phi_pii_columns_file: configs/phi_pii_columns.yaml
      # Mandatory; only these normalized columns may contain complete dates.
      date_screening_policy_file: configs/all_als_date_screening.yaml
      # Or pass --preflight-report at runtime for a local Markdown report.
      preflight_report: annotations/all_als_preflight_report.md
      # DANGEROUS: makes terminal/report output contain raw date values.
      include_violation_values: false
```

`Form Name`/`form_name`, `NeuroGUID`, `NeuroSTAmP`, and `visit_name` are ignored
only for dictionary equality; `NeuroGUID` and `NeuroSTAmP` remain required in
every file. `localUID` is forbidden by the PHI/PII header policy; `SubjectUID` is
not a required ALL ALS header. `dictionary_exceptions` removes legacy
`localUID`, `subjectUID`, `siteUID`, `initials`, `reason_for_failure`, `state`,
and `visit` definitions from exact dictionary coverage and reports a warning for
each dictionary view that still defines them. The demographics requirement uses
the canonical raw ALL ALS view name, not a friendly alias. Alias mapping is
intentionally deferred.

The required header policy file is `configs/phi_pii_columns.yaml`; it fails if a
normalized forbidden PHI/PII name occurs. The mandatory value policy is
`configs/all_als_date_screening.yaml`: complete dates and date-times are rejected
in every cell, including free text, unless the normalized column is explicitly
allowlisted for collection/assessment dates. Native Excel dates and ISO, slash,
hyphen, and month-name date strings are screened. Standalone four-digit years are
reported as non-blocking warnings. Neither policy logs cell values by default;
raw date values are emitted only with the dangerous explicit
`--include-violation-values` option above. Missing or malformed policies, unknown
views, duplicate headers, missing required headers,
extra/missing dictionary headers, forbidden headers, or disallowed dates halt the
workflow before annotation output. The checker completes all readable staged files
and reports every violation together; a corrupt/unsupported file is recorded while
other files continue to be checked. One unnamed first header is treated as a
row-index column and reported as a warning; blank headers elsewhere still fail. Do
not disable either gate with a CLI flag.

The date policy is version-controlled and fail-closed:

```yaml
version: 1
allowed_columns:
  all_files: [collection_date, assessment_date]
  # Applies to every canonical raw view whose normalized name starts with prefix.
  by_view_prefix:
    v_ALLALS_AS: [mh_clin_dat]
    v_ALLALS_PR: [prstdat]
  by_view:
    v_ALLALS_AS_ASSEDEMOG: [demographics_assessment_date]
```

Do not add broad free-text exceptions. Reports contain only filenames, views,
columns, counts, and row numbers—not source cell values unless the dangerous
explicit value-output option is used. See [the ALL ALS preflight
plan](ALL_ALS_UPDATE_PREFLIGHT_PLAN.md) for details and future semantic
screening/alias work.

### ALL ALS reviewed match manifest

After ALL ALS preflight passes, the first Phase-1 `update` run writes
`annotations/<Dataset Name>_match_manifest.json` and stops before mapping or
annotation-template generation. Review exact target/source IDs, additions, and
any ambiguity; resolve release-specific exceptions in the manifest, then set
`"status": "approved"`. Rerun the same `update` command to validate the
manifest snapshots and generate mappings plus file/Dataset annotation templates.
A changed Dataset member or staging source makes the manifest stale. ALL ALS
never uses fuzzy matching in this flow; files with `viewName` are constrained by
canonical view, and Form Name only disambiguates files sharing that view. Dataset
members that are data dictionaries are emitted with the `MetadataSchema` file type,
not the clinical record-file schema. Configure an exact raw-to-canonical alias under
`update.all_als.view_aliases` when a raw
staging filename intentionally differs from the data-dictionary view.

## 20. Clean PHI/PII Columns from Every File Version

This is deliberately a two-step workflow. Step 1 recursively lists only folder/file metadata and writes an editable map: **it does not download or inspect file bytes**. Use Synapse IDs (the default) so duplicate filenames are unambiguous.

```bash
# Step 1: metadata-only recursive scaffold. Edit each [] with exact column headers.
mamba run -n amp-als python scripts/clean_phi_files.py \
  --folder syn77348789 \
  --write-column-map annotations/files_to_clean_columns.json

# Step 2: download every version only after the reviewed map is complete,
# remove those columns, and keep cleaned copies locally.
mamba run -n amp-als python scripts/clean_phi_files.py \
  --folder syn77348789 \
  --column-map annotations/files_to_clean_columns.json \
  --output-dir cleaned_files

# Optional: also upload all cleaned versions, in source-ID/version order, as the
# version history of one new Synapse File entity in the target folder.
mamba run -n amp-als python scripts/clean_phi_files.py \
  --folder syn77348789 \
  --column-map annotations/files_to_clean_columns.json \
  --output-dir cleaned_files \
  --upload-folder synTARGET_FOLDER --merged-name "Files_To_Remove_and_Clean_cleaned.csv" \
  --execute
```

`scripts/clean_phi_files.py` is standalone: it does not import or invoke `synapse_dataset_manager`. The map format is `{ "synId": ["PHI column", "PII column"] }`; filenames can be used as keys only when unique. CSV, TSV, XLSX, and XLSM are supported. Cleaning stops if a designated header is absent in any selected version, preventing a silently incomplete PHI/PII removal. `--upload-folder` requires both `--merged-name` and `--execute`; local output never uploads anything. See [CLEAN_PHI_FILES.md](CLEAN_PHI_FILES.md) for setup, map review, local export, and upload-only workflows.

## 21. Audit Release Versions Against Staging Checksums

Compare each release File version with the latest version of its corresponding raw staging file using only metadata (version label, `viewName`, MD5, and size). This command **never downloads file content**. Supply one `LABEL=SYNID` pair for every staging release folder being audited; the label must match the release version label.

```bash
mamba run -n amp-als python -m synapse_dataset_manager audit-release-staging \
  --release-folder syn76959294 \
  --cohort PREVENT \
  --staging-folder \
    v2-OCT=syn70781123 \
    v3-DEC=syn71824454 \
    v4-JAN=syn72662626 \
    v5-FEB=syn73806457 \
    v6-MAR=syn74144528 \
    v7-APR=syn74544389 \
    v8-MAY=syn74956654 \
    v9-JUNE=syn75362825 \
    v10-JULY=syn76306929 \
    v11-AUG=syn76900556 \
    v12-SEPT=syn77568843 \
  --output annotations/prevent_release_staging_audit.json \
  --fail-on-mismatch
```

The command derives a staging filename as `{view_name}.csv` from each release version's `viewName` annotation. Use `--source-name-map aliases.json` for exceptions, where `aliases.json` is a JSON object such as:

```json
{
  "v_ALLALS_PR_PREVELIGCRITGEN2": "v_ALLALS_PR_PREVELIGCRTGEN2.csv"
}
```

Use `--view-annotation` to select a different identifying annotation and `--source-name-template` to change the default raw-file naming convention. The JSON report separates exact matches, checksum mismatches, and unresolved versions (for example, when a staging file was moved or a historical annotation is absent).

## 22. Rebuild File Entity Version Histories from Staging Sources

Rebuild one or more File entities from explicitly listed staging folders and exact source filenames. The command is generic: it does not infer sources from `viewName`, cohort names, dates, or project-specific conventions. Without `--execute`, it validates the manifest and produces a metadata-only plan—no file bytes are downloaded.

Create a manifest such as `rebuild_manifest.json`:

```json
{
  "output_folder": "synOUTPUT",
  "targets": [
    {
      "key": "corrected_file",
      "output_name": "Corrected release file.csv",
      "source_filename": "raw_source.csv",
      "original_entity_id": "synOLD_RELEASE_FILE",
      "annotation_source_entity_id": "synOLD_RELEASE_FILE",
      "sources": [
        {
          "folder_id": "synSTAGING_OCT",
          "label": "v2-OCT",
          "comment": "October release"
        },
        {
          "folder_id": "synSTAGING_NOV",
          "label": "v3-NOV",
          "source_filename": "renamed_raw_source.csv",
          "annotation_source": {"entity_id": "synOLD_RELEASE_FILE", "version": 7}
        }
      ]
    }
  ]
}
```

Preview the resolved source versions:

```bash
mamba run -n amp-als python -m synapse_dataset_manager rebuild-file-entity \
  --manifest rebuild_manifest.json \
  --output annotations/rebuild_plan.json
```

After reviewing the plan, create the replacement entity history. The default interactive mode lets you choose the annotation source for each output version; use `--annotation-mode auto` to use the manifest/default annotation sources without prompts.

```bash
mamba run -n amp-als python -m synapse_dataset_manager rebuild-file-entity \
  --manifest rebuild_manifest.json \
  --execute \
  --output annotations/rebuild_result.json
```

Execution requires `--output` and uses create-only File creation: a name collision
fails rather than updating an existing File. It never modifies a Dataset; legacy
`dataset_id` manifest values are ignored with a warning. The report is written atomically
throughout execution, including partial IDs and versions. On any failure, especially a
store timeout, inspect Synapse and the report before retrying: the remote outcome can be
unknown. Failed reports cannot be used to generate Dataset manifests. Validate the new
history and update references separately before retiring an old entity.

## Audit a reconstructed Dataset

Compare the approved manifest and completed execution report with the current source
baseline and every rebuilt snapshot without mutating Synapse or downloading Dataset Files:

```bash
mamba run -n amp-als python -m synapse_dataset_manager audit-dataset-rebuild \
  --manifest dataset_rebuild.json --report dataset_rebuild_result.json \
  --output dataset_audit.json
```

The audit checks the replacement Dataset ID, type, name and parent, its full version
list, pinned membership, annotations, labels, comments, schema and wiki header
titles/hierarchy. A renamed or moved Dataset fails the identity check, even if the
change was intentional; the output includes actual and expected identity values for
operator review. It fails on differences or source baseline drift. Wiki attachments
are an explicit exception and require manual reattachment. Markdown is **not checked**
by default; add `--wiki-markdown` to download and compare wiki markdown. A passing
metadata-only audit does not establish markdown or attachment equivalence.

## Mint a DOI for a Dataset (experimental)

After a successful rebuild, separately consider minting a DOI; rebuilding never mints one.
Preview checks Dataset metadata and the absence of an association, without writing:

```bash
mamba run -n amp-als python -m synapse_dataset_manager mint-dataset-doi \
  --dataset-id syn123 --creator 'Example, Alice' --title 'Example Dataset' --year 2025
```

Default is an unversioned DOI pointing to the latest Dataset. Add `--version 4` to
explicitly pin snapshot 4. Repeat `--creator` for multiple creators. To submit once:

```bash
mamba run -n amp-als python -m synapse_dataset_manager mint-dataset-doi \
  --dataset-id syn123 --creator 'Example, Alice' --title 'Example Dataset' --year 2025 \
  --execute --confirm syn123:latest --coordinate --acknowledge-production \
  --output doi-syn123-recovery.json
```

For a pinned version confirm `syn123:4`. `--coordinate` affirms that the operator has
coordinated with all other DOI writers; `--acknowledge-production` acknowledges the
production, potentially irreversible operation. Synapse's endpoint creates **or updates**:
another client can race between the preflight and POST, and no client-side check can
prevent this without a server atomic create-only operation. Coordinate externally.
The exclusive output path is reserved and durably saved before the single POST; its
status is marked unknown before submission, then the returned token is saved before
polling. A timeout, lost response, crash, or verification failure is not permission to
resubmit. Investigate the report, token and Synapse association manually. Polling is
bounded by `--poll-timeout` (default 120 seconds); client REST retries are disabled.
Synapse itself may retry downstream DataCite work. A report marked completed means the
returned association ID, target, version and DOI URI passed verification, not that an
independent client race was impossible. Pinned submission is not sandbox-validated.
See [rebuild notes](REBUILD_FILE_AND_DATASET_ENTITIES.md#doi-policy).

## Help Commands

```bash
# Main help
python synapse_dataset_manager.py --help
mamba run -n amp-als python -m synapse_dataset_manager --help
mamba run -n amp-als python -m synapse_dataset_manager update --help

# Command-specific help
python synapse_dataset_manager.py update --help  # workflow, identity, dictionary, --write-plan, --plan-file
python synapse_dataset_manager.py generate-template --help
python synapse_dataset_manager.py generate-mapping --help
python synapse_dataset_manager.py generate-file-templates --help
python synapse_dataset_manager.py create --help  # includes mapping flags
python synapse_dataset_manager.py add-link-file --help
python synapse_dataset_manager.py create-entity-view --help
python synapse_dataset_manager.py reorder-columns --help
python synapse_dataset_manager.py rename-annotation --help
python synapse_dataset_manager.py move --help
python synapse_dataset_manager.py delete-entities --help
python synapse_dataset_manager.py clean-phi-files --help
python synapse_dataset_manager.py audit-release-staging --help
python synapse_dataset_manager.py rebuild-file-entity --help
python synapse_dataset_manager.py generate-file-rebuild-manifest --help
python synapse_dataset_manager.py generate-dataset-rebuild-manifest --help
python synapse_dataset_manager.py rebuild-dataset-entity --help
python synapse_dataset_manager.py audit-dataset-rebuild --help
python synapse_dataset_manager.py mint-dataset-doi --help
python scripts/clean_phi_files.py --help
```
