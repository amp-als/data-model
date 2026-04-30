# Upload Local Workflow

## Overview

The `upload-local` command uploads a local directory of files to a new Synapse folder, generates annotation templates, and adds the uploaded files to one or more existing datasets.

It is designed for cases where files already exist locally and need to be uploaded as **new Synapse entities** — not as new versions of existing files. The classic example is uploading unzipped speech data that was previously stored on Synapse as zipped archives: the unzipped files are structurally different enough to warrant new entities rather than new versions.

The workflow is intentionally simpler than `update`. There is no form-name matching, no viewName logic, and no staging folder enumeration — just a direct local-to-Synapse upload followed by annotation and dataset membership.

## When to Use

- Files exist locally and need to be uploaded to Synapse for the first time (or as new entities, not new versions)
- Files are not tracked in the existing dataset yet — they need to be added after upload
- Files do not have viewNames or form names (e.g., speech/audio data, subject-folder-organized data)
- The same set of uploaded files needs to be added to multiple datasets (e.g., both ASSESS and PREVENT)

## Prerequisites

```bash
mamba activate amp-als
```

**Before running Phase 1**, rename your local folders from localUID to SubjectUID using your mapping file. The workflow uploads whatever directory structure it finds — it does not perform renaming itself. See [Renaming Local Folders](#renaming-local-folders) below.

## Two-Phase Workflow

| Phase | Trigger | What it does |
|-------|---------|--------------|
| Phase 1 | No `--annotations-file` | Creates Synapse folder structure, uploads files, writes annotation template JSON |
| Phase 2 | `--annotations-file` provided | Validates, applies annotations to uploaded files, adds files to dataset(s) |

---

## CLI Usage

### Arguments

| Argument | Phase | Required | Description |
|----------|-------|----------|-------------|
| `--local-dir` | 1 | Yes | Local directory of files to upload |
| `--parent-folder` | 1 | Yes | Synapse ID of the parent folder to create the target subfolder under |
| `--folder-name` | 1 | No | Name for the new Synapse subfolder (defaults to local dir name) |
| `--file-type` | 1 | No | Schema file type for annotation templates (default: `ClinicalFile`) |
| `--dataset-id` | 1 & 2 | No | Synapse dataset ID(s) to add uploaded files to — accepts multiple IDs |
| `--annotations-file` | 2 | Yes | Path to edited annotations JSON — triggers Phase 2 |
| `--version-label` | 2 | No | Version label to set on files (e.g., `"v1-APR"`) |
| `--version-comment` | 2 | No | Version comment for uploaded files |
| `--skip-validation` | 2 | No | Skip annotation schema validation before applying |
| `--execute` | Both | No | Execute (overrides DRY_RUN in config) |
| `--dry-run` | Both | No | Dry run mode — preview actions without making changes (default) |

---

### Phase 1: Upload and Generate Template

```bash
python synapse_dataset_manager.py upload-local \
  --local-dir /path/to/renamed_speech_data \
  --parent-folder syn<RELEASE_FOLDER_ID> \
  --folder-name "Speech" \
  --file-type ClinicalFile \
  --dataset-id syn<DATASET_ID> \
  --execute
```

This will:
1. Create (or find existing) a `Speech/` subfolder under the specified parent folder
2. Mirror the local subdirectory structure as Synapse Folder entities
3. Upload every file, preserving the folder hierarchy
4. Generate `annotations/<folder_name>_upload_annotations.json` with an empty template for each file

Output example:
```
WORKFLOW: UPLOAD LOCAL FILES
Phase: 1 — Upload & Template Generation

STEP 1: RESOLVING TARGET FOLDER ON SYNAPSE
  Parent   : syn12345678
  Subfolder: Speech
  ✓ Created folder 'Speech' → syn99999901

STEP 2: UPLOADING LOCAL FILES
  Source: /path/to/renamed_speech_data
  ✓ sub-001/recording_01.wav → syn99999902
  ✓ sub-001/recording_02.wav → syn99999903
  ✓ sub-002/recording_01.wav → syn99999904
  ...
  Uploaded: 42 files → 42 entities

STEP 3: GENERATING ANNOTATION TEMPLATES
  Default file type: ClinicalFile
✓ Saved annotations to annotations/Speech_upload_annotations.json

✅ PHASE 1 COMPLETE
  Uploaded     : 42 files
  Target folder: syn99999901
  Template file: annotations/Speech_upload_annotations.json

⚠️  MANUAL STEP: Edit the annotation file, then re-run with:
  python synapse_dataset_manager.py upload-local \
    --annotations-file annotations/Speech_upload_annotations.json \
    --dataset-id syn<DATASET_ID> \
    --execute
```

**After Phase 1:** Open `annotations/Speech_upload_annotations.json` and fill in the required annotation fields for each file. The template will contain empty values for all fields defined in the schema for the specified `--file-type`.

---

### Phase 2: Apply Annotations and Add to Dataset(s)

```bash
python synapse_dataset_manager.py upload-local \
  --annotations-file annotations/Speech_upload_annotations.json \
  --dataset-id syn<DATASET_ID_1> syn<DATASET_ID_2> \
  --execute
```

This will:
1. Load and validate the edited annotations JSON
2. Apply annotations to each uploaded file on Synapse
3. Add all files to each specified dataset

To add the same files to both ASSESS and PREVENT datasets, list both dataset IDs:
```bash
  --dataset-id syn<ASSESS_DATASET_ID> syn<PREVENT_DATASET_ID>
```

---

### Dry Run (Preview)

Always preview before executing:

```bash
# Phase 1 dry run — shows what folders would be created and files uploaded
python synapse_dataset_manager.py upload-local \
  --local-dir /path/to/renamed_speech_data \
  --parent-folder syn<RELEASE_FOLDER_ID> \
  --folder-name "Speech" \
  --dry-run

# Phase 2 dry run — shows what annotations would be applied
python synapse_dataset_manager.py upload-local \
  --annotations-file annotations/Speech_upload_annotations.json \
  --dataset-id syn<DATASET_ID> \
  --dry-run
```

> **Note:** Phase 1 dry run does not write an annotations file, since there are no real Synapse IDs to reference. Run Phase 1 with `--execute` to get a usable template.

---

## Separate Runs for Multiple Datasets

If ASSESS and PREVENT speech files live in different release folders, run Phase 1 separately for each:

```bash
# ASSESS speech
python synapse_dataset_manager.py upload-local \
  --local-dir /path/to/assess_speech \
  --parent-folder syn<ASSESS_RELEASE_FOLDER> \
  --folder-name "Speech" \
  --dataset-id syn<ASSESS_DATASET_ID> \
  --execute

# PREVENT speech
python synapse_dataset_manager.py upload-local \
  --local-dir /path/to/prevent_speech \
  --parent-folder syn<PREVENT_RELEASE_FOLDER> \
  --folder-name "Speech" \
  --dataset-id syn<PREVENT_DATASET_ID> \
  --execute
```

Each run produces its own annotations JSON. Edit them independently, then run Phase 2 for each.

---

## Renaming Local Folders

The `upload-local` workflow uploads whatever directory structure it finds — it does not rename folders. **Rename local folders from localUID to SubjectUID before running Phase 1.**

A simple rename script using a mapping CSV (`localUID,subjectUID`):

```python
import os
import csv

mapping_file = "localUID_to_subjectUID.csv"
local_dir    = "/path/to/speech_data"

with open(mapping_file) as f:
    mapping = {row["localUID"]: row["subjectUID"] for row in csv.DictReader(f)}

for entry in os.scandir(local_dir):
    if entry.is_dir() and entry.name in mapping:
        new_name = mapping[entry.name]
        os.rename(entry.path, os.path.join(local_dir, new_name))
        print(f"  {entry.name} → {new_name}")
```

Run this once, verify the folder names look correct, then proceed with `upload-local`.

---

## Folder Structure on Synapse

Given a local directory like:
```
speech_data/
  sub-001/
    recording_01.wav
    recording_02.wav
  sub-002/
    recording_01.wav
```

With `--parent-folder syn<PARENT>` and `--folder-name Speech`, the resulting Synapse structure will be:
```
<PARENT>/
  Speech/
    sub-001/
      recording_01.wav
      recording_02.wav
    sub-002/
      recording_01.wav
```

Existing subfolders with the same name are reused rather than duplicated, so re-running Phase 1 after a partial failure will not create duplicate folders.

---

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| `--folder-name` not provided | Defaults to the base name of `--local-dir` |
| Target subfolder already exists | Reuses the existing folder — does not create a duplicate |
| Subdirectory with no files | Skipped — empty folders are not created on Synapse |
| File upload fails mid-run | Error is printed and skipped; other files continue uploading. Rerun Phase 1 to retry (existing folders are reused) |
| `--dataset-id` not provided in Phase 2 | Annotations are applied but files are not added to any dataset — Step 4 is skipped |
| Multiple `--dataset-id` values | Files are added to each dataset in sequence |

---

## Troubleshooting

### Phase 1 produces no annotations file
Phase 1 only writes the template when `--execute` is passed. Dry run mode skips the file write since there are no real Synapse IDs.

### Annotations file has `syn_DRY_XXXX` IDs
You ran Phase 1 in dry-run mode. Re-run with `--execute` to upload the files and generate a valid annotations file with real Synapse IDs.

### Validation errors in Phase 2
Edit the annotations JSON to fix the flagged fields. If the errors are in non-critical fields you want to skip, re-run Phase 2 with `--skip-validation`.

### Files added to dataset but annotations not applied
Phase 3 (apply annotations) and Phase 4 (add to dataset) are independent steps within Phase 2. Check the `Applied/Skipped/Errors` counts in the Step 3 output. If annotations were skipped due to no detected changes, verify that the JSON was saved after editing.
