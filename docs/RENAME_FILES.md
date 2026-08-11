# Rename Files

## Overview

The `rename-files` command renames Synapse **file entities** — both the entity
display name and the download filename — **without re-uploading the underlying
data**.

Under the hood it uses `synapseutils.changeFileMetaData`, which copies the
existing file handle *server-side* (pointing at the same stored object) when the
download filename changes. No bytes are transferred and nothing is re-uploaded,
so renames are effectively instant regardless of file size.

Because datasets and dataset collections reference files by their Synapse ID
(not by name), renaming files does **not** break dataset membership.

## When to Use

- A file was uploaded with the wrong name and you want to fix it without a
  costly re-upload
- You need to bulk-rename many files from a mapping (e.g. localUID → SubjectUID)
- You want to strip or rewrite a common prefix/suffix across every file in a
  dataset or collection (e.g. remove `GSE126541_` from accession-prefixed names)

## Prerequisites

```bash
# Activate environment
mamba activate amp-als
```

## What Gets Renamed

By default **both** of these are updated to the new name:

| Name | What it is | Cost |
|------|-----------|------|
| Entity display name (`entity.name`) | What shows in the Synapse UI and dataset tables | Metadata-only |
| Download filename (file handle `fileName`) | The filename you get when you download the file | Server-side file-handle copy — **no re-upload** |

Use `--name-only` to change just the entity display name and leave the download
filename untouched.

## Versioning

By default renaming does **not** create a new file version. Pass `--new-version`
to force a version bump.

## Targeting Modes

`rename-files` supports three mutually exclusive ways to select what to rename.

### Mode 1 — Single file

```bash
python synapse_dataset_manager.py rename-files \
  --file-id syn12345678 \
  --new-name "sample_01_rnaseq.fastq.gz" \
  --execute
```

### Mode 2 — Batch mapping file

Provide a mapping of Synapse ID → new name. Two formats are accepted:

**JSON** (`renames.json`) — comments (`#`) and trailing commas are tolerated:

```json
{
  "syn12345678": "sample_01_rnaseq.fastq.gz",
  "syn12345679": "sample_02_rnaseq.fastq.gz"
}
```

**CSV / XLSX** — with a Synapse-ID column (`synId`, `synapseId`, or `id`) and a
new-name column (`new_name`, `newName`, or `name`):

```csv
synId,new_name
syn12345678,sample_01_rnaseq.fastq.gz
syn12345679,sample_02_rnaseq.fastq.gz
```

```bash
python synapse_dataset_manager.py rename-files \
  --mapping-file renames.json \
  --execute
```

### Mode 3 — Pattern across a dataset or collection

Enumerate every file in a dataset (`--dataset-id`) or across all datasets in a
collection (`--collection-id`) and apply a find/replace to each file's current
name. Only files whose name actually changes are touched; when a collection
lists the same file in multiple datasets it is renamed once.

```bash
# Literal substring replace — strip a suffix from every file in a dataset
python synapse_dataset_manager.py rename-files \
  --dataset-id syn67890 \
  --find " (copy)" --replace "" \
  --execute

# Regex replace — drop a leading accession prefix across a whole collection
python synapse_dataset_manager.py rename-files \
  --collection-id syn66496326 \
  --regex --find "^GSE[0-9]+_" --replace "" \
  --execute
```

## Arguments

| Argument | Mode | Description |
|----------|------|-------------|
| `--file-id` | Single | Synapse ID of the file to rename (use with `--new-name`) |
| `--new-name` | Single | New name for the file |
| `--mapping-file` | Batch | JSON `{synId: newName}` or CSV/XLSX with `synId,new_name` columns |
| `--dataset-id` | Pattern | Rename files in this dataset (use with `--find`/`--replace`) |
| `--collection-id` | Pattern | Rename files across all datasets in this DatasetCollection |
| `--find` | Pattern | Substring (or regex with `--regex`) to find in current file names |
| `--replace` | Pattern | Replacement string |
| `--regex` | Pattern | Treat `--find` as a regular expression (`re.sub`) |
| `--name-only` | All | Only change the entity display name; leave the download filename unchanged |
| `--new-version` | All | Force a new file version (default: no version bump) |
| `--verbose` | All | Print detailed info for each file processed |
| `--execute` | All | Apply changes (overrides DRY_RUN) |
| `--dry-run` | All | Preview mode — show what would happen without making changes (default) |

## Dry Run First

Like the other write commands, `rename-files` runs in **dry-run mode by
default**. Always preview before executing:

```bash
# Preview — shows "name 'old' → 'new'; downloadAs 'old' → 'new'" per file
python synapse_dataset_manager.py rename-files \
  --dataset-id syn67890 --find "raw_" --replace "" --dry-run

# Apply once the preview looks correct
python synapse_dataset_manager.py rename-files \
  --dataset-id syn67890 --find "raw_" --replace "" --execute
```

## Related Commands

- `rename-folders` — rename **folder** entities matching a pattern across a
  collection
- `rename-annotation` — rename an annotation **key** across datasets/files
- `merge-file-versions` — consolidate two entities' version histories (see
  [MERGE_FILE_VERSIONS.md](MERGE_FILE_VERSIONS.md))
