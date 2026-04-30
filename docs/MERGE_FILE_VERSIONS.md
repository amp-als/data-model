# Merge File Versions

## Overview

The `merge-file-versions` command merges the version histories of two Synapse file entities into a single new file entity. This is useful when the same logical file was accidentally split across two separate entities, each containing part of the version history.

The command downloads all versions from both files, lets you interactively select and order which versions to include, resolves any duplicate version labels, then creates a new merged file entity with the combined version history.

## When to Use

- Two file entities represent the same file but have separate version histories due to accidental duplication
- You need to consolidate versions from multiple entities into one clean version history
- Manual version-by-version download and re-upload is too tedious

## Prerequisites

```bash
# Activate environment
mamba activate amp-als
```

Both files must:
- Be file entities (not folders or datasets)
- Live in the same parent folder on Synapse

## CLI Usage

### Basic Command

```bash
python synapse_dataset_manager.py merge-file-versions \
  --file-1-synid <SYN_ID> \
  --file-2-synid <SYN_ID>
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--file-1-synid` | Yes | Synapse ID of the first file entity |
| `--file-2-synid` | Yes | Synapse ID of the second file entity |
| `--merged-name` | No | Name for the merged file (defaults to file 1's name) |
| `--execute` | No | Execute the merge (overrides DRY_RUN) |
| `--dry-run` | No | Preview mode — show what would happen without making changes (default) |

### Examples

```bash
# Dry run — preview the merge without making changes
python synapse_dataset_manager.py merge-file-versions \
  --file-1-synid syn71824499 \
  --file-2-synid syn68905831 \
  --dry-run

# Execute the merge
python synapse_dataset_manager.py merge-file-versions \
  --file-1-synid syn71824499 \
  --file-2-synid syn68905831 \
  --execute

# Execute with a custom name for the merged file
python synapse_dataset_manager.py merge-file-versions \
  --file-1-synid syn71824499 \
  --file-2-synid syn68905831 \
  --merged-name "Pre-Test Genetic Counseling Appointment.csv" \
  --execute
```

## Interactive Workflow

The command walks you through several interactive steps:

### Step 1: Validation

The tool validates that both Synapse IDs point to file entities in the same parent folder and displays their names.

### Step 2: Fetch Version Histories

All versions of both files are fetched, including their annotations, labels, comments, and sizes.

### Step 3: Version Selection and Ordering

A table is displayed showing all available versions from both files:

```
================================================================================
AVAILABLE VERSIONS
================================================================================

File 1: syn71824499 (PreTest Genetic Counseling Appointment.csv)
  Tag               | Ver# | Label               | Comment                  | Modified            | Size
  ----------------------------------------------------------------------------
  File_1-v1         |    1 | 1                   |                          | 2025-12-02          | 20.0 KB
  File_1-v2         |    2 | 2                   |                          | 2026-01-08          | 20.0 KB
  File_1-v3         |    3 | v4-JAN              | Jan Release              | 2026-02-18          | 24.6 KB
  ...

File 2: syn68905831 (Pre-Test Predictive Genetic Counseling Appointment)
  Tag               | Ver# | Label               | Comment                  | Modified            | Size
  ----------------------------------------------------------------------------
  File_2-v1         |    1 | 1                   |                          | 2025-09-05          | 10.9 KB
  File_2-v2         |    2 | 2                   | changed v_ALLALS_PR...   | 2025-09-08          | 10.9 KB
  ...
```

**Tags** use the format `File_1-v{version_number}` and `File_2-v{version_number}`.

A **suggested order** is displayed, sorted by the original `modifiedOn` date (earliest first). Press ENTER with no input to accept it, or type a custom comma-separated order:

```
Suggested: File_2-v1,File_2-v2,File_1-v1,File_1-v2,File_1-v3,File_1-v4,File_1-v5,File_2-v4,File_2-v5

Selection:                <-- press ENTER to accept suggested order
Selection: File_2-v1,...  <-- or type a custom order
```

- The **first** tag becomes version 1 (earliest) of the merged file
- The **last** tag becomes the current/latest version
- You can omit versions you don't want to include (use a custom order)

### Step 4: Duplicate Label Resolution

If two selected versions have the same version label (e.g., both files have a version labeled "1"), you are prompted to resolve each conflict:

```
DUPLICATE VERSION LABELS DETECTED

  Label '1' appears in 2 selected versions:
    Position 1: syn68905831 version 1 (comment: 'none')
    Position 3: syn71824499 version 1 (comment: 'none')

  Options for label '1':
    drop <position>   - Remove that version from the merge
    rename <position> <new_label> - Rename that version's label
```

**Options:**
- `drop 1` — removes the version at position 1 from the merge entirely
- `rename 1 Initial_Release` — renames position 1's label to `Initial_Release`

### Step 5: Confirmation

A preview of the resulting version history is shown in descending order (matching the Synapse UI), with the latest version marked:

```
RESULTING VERSION HISTORY — PreTest Genetic Counseling Appointment.csv

  Version  Label                   Source                        Comment                         Size
  ----------------------------------------------------------------------------------------------------
        9  v7-APR                  syn68905831 v5                April Release                   30.0 KB    (current)
        8  v6-MAR                  syn68905831 v4                March Release                   27.4 KB
        7  v5-FEB                  syn71824499 v5                Feb Release                     25.0 KB
        ...
        1  Initial_Release         syn68905831 v1                                                10.9 KB

Does this look correct? Proceed? [y/N]:
```

Review the table carefully. If it doesn't look right, type `N` and re-run.

### Step 6: Merge Execution

The tool:
1. Creates a temporary folder (`_merge_temp_<timestamp>`) in the parent directory
2. Downloads each selected version from its source entity
3. Uploads them in order to a new file entity, preserving annotations, labels, and comments

### Step 7: Summary and Next Steps

After the merge completes, a summary is printed:

```
MERGE SUMMARY
  New file entity   : syn99999999
  Temp folder       : syn88888888 (_merge_temp_20260428_190000)
  Versions uploaded : 9
  Errors            : 0
  Original File 1   : syn71824499 (NOT deleted)
  Original File 2   : syn68905831 (NOT deleted)

  NEXT STEPS:
    1. Verify the merged file at https://www.synapse.org/Synapse:syn99999999
    2. Move syn99999999 from temp folder to parent folder syn68885187
    3. Delete original files syn71824499 and syn68905831
    4. Delete temp folder syn88888888
```

**The original files are never deleted automatically.** You must manually verify the merged result and perform cleanup steps yourself.

## What Gets Preserved

For each version uploaded to the merged file:
- **File content** — the actual file bytes from the source version
- **Version label** — the label from the source (or renamed label if there was a conflict)
- **Version comment** — the comment from the source version, with the original modified date prepended (e.g., `[Original date: 2025-12-02] Jan Release`). Synapse always sets `modifiedOn` to the upload time with no API to override it, so the original date is preserved in the comment instead.
- **Annotations** — all annotations from the source version at that point in time

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| Files in different parent folders | Error — both must be in the same folder |
| Files with different names | Defaults to file 1's name; use `--merged-name` to override |
| Duplicate version labels | Interactive resolution — drop one or rename |
| Version with no label | Uses the version number as the label |
| Empty version comment | Explicitly set to empty (won't carry over previous comment) |

## Troubleshooting

### Size Mismatch Warnings

If you see `Size mismatch: expected ~X, got Y` during download, the Synapse client cache may be stale. The tool automatically clears cache entries before each download, but if issues persist:

```bash
# Clear the entire Synapse cache
rm -rf ~/.synapseCache
```

Then re-run the command.

### Version Label Already Exists

If you see `Version label 'X' already exists — skipping`, this means a label collision was not caught during the resolution step. Re-run the merge and ensure all duplicate labels are resolved.
