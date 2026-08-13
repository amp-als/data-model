# Upload Staged Version

## Overview

The `upload-staged-version` command uploads a single staging file as a new version of one existing Synapse file entity. It preserves that entity's current annotations — no annotations JSON is required.

It exists as a lightweight alternative to the `update` command's staging-based version upload (`upload_new_versions_from_staging`), which requires generating a full annotations template (Phase 1) and editing/validating it (Phase 2) even to bump a single file's version. `upload-staged-version` skips all of that: point it at the existing entity and the staging file, and it does the download + re-upload in one step.

## When to Use

- A single file's content changed (e.g., a corrected CSV re-exported to a staging folder) and you just need to push it as a new version
- You don't want to run the full `update` workflow (template generation → edit → apply) for a one-off fix
- The file's annotations don't need to change — only the content/version

If you're updating many files at once, or need to change annotations alongside the content, use `update` instead (see [`docs/AGENTS.md`](AGENTS.md) and the `update` command's `--help`).

## Prerequisites

```bash
mamba activate amp-als
```

You need:
- The Synapse ID of the **existing** file entity to version (`--syn-id`)
- The Synapse ID of the **staging** file containing the new content (`--staging-id`)

## CLI Usage

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--syn-id` | Yes | Synapse ID of the existing file entity to create a new version of |
| `--staging-id` | Yes | Synapse ID of the staging file with the new content |
| `--version-label` | No | Version label for the new version (e.g., `"v4-JAN"`) |
| `--version-comment` | No | Version comment for the new version |
| `--execute` | No | Execute (overrides DRY_RUN in config) |
| `--dry-run` | No | Dry run mode — preview without making changes (default) |

### Examples

```bash
# Dry run — preview without making changes
python synapse_dataset_manager.py upload-staged-version \
  --syn-id syn12345 \
  --staging-id syn67890 \
  --version-label v4-JAN \
  --version-comment "Corrected subject IDs" \
  --dry-run

# Execute
python synapse_dataset_manager.py upload-staged-version \
  --syn-id syn12345 \
  --staging-id syn67890 \
  --version-label v4-JAN \
  --version-comment "Corrected subject IDs" \
  --execute
```

## What It Does

1. Fetches the existing entity (`--syn-id`) and reads its current annotations — these are carried over unchanged.
2. Downloads the staging file (`--staging-id`) to a temporary local directory.
3. Uploads the downloaded content to `--syn-id`, creating a new version with the given `--version-label`/`--version-comment` and the preserved annotations.

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| `--version-label` already exists on the target entity | Upload is skipped with a `[SKIP]` message (Synapse rejects duplicate revision labels) |
| Staging file fails to download | Error is printed, command exits non-zero |
| `--syn-id` doesn't exist or isn't accessible | Error is printed, command exits non-zero |
| `--dry-run` (default) | No download or upload occurs; prints what would happen |

## Related

- [`docs/AGENTS.md`](AGENTS.md) — full command reference and repo structure
- [`update` command](../synapse_dataset_manager.py) — batch version of this workflow, driven by an annotations JSON (`upload_new_versions_from_staging`)
- [`UPLOAD_LOCAL_WORKFLOW.md`](UPLOAD_LOCAL_WORKFLOW.md) — for uploading files as **new entities**, not new versions of existing ones
