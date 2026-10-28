# Reviewed update plans

`update` now separates annotation preparation, plan review, and execution. The
shared implementation lives in:

- `synapse_dataset_manager/updates/plans.py`: action compilation, fingerprints,
  artifact validation, and stale-plan comparisons.
- `synapse_dataset_manager/updates/engine.py`: review, preflight, fail-fast
  execution, and checkpointed reports.
- `synapse_dataset_manager/updates/operations.py`: Synapse reads, pinned downloads,
  uploads, annotation changes, moves, dataset reference updates, and verification.

Both `general` and `all_als` use the same engine. The old batch update execution
helpers have been removed from `cli.py`; unrelated commands retain their existing
behavior. No live Synapse writes are required for the offline test suite.

## 1. Prepare and edit annotations

Use the existing phase-1 command, with `--workflow all_als` when appropriate:

```bash
mamba run -n amp-als python -m synapse_dataset_manager update \
  --dataset-id syn123 --staging-folder syn456
```

Edit the generated annotations JSON. Existing `_staging_id` artifacts remain
supported: a dry run compiles them into explicit actions. They cannot bypass plan
review. There is no implicit rename of an existing entity; use the separate
rename command when necessary, then prepare a new plan.

## 2. Generate a plan without remote writes

```bash
mamba run -n amp-als python -m synapse_dataset_manager update \
  --dataset-id syn123 \
  --annotations-file annotations/Example_update_annotations.json \
  --release-folder syn789 --version-label v2 \
  --write-plan annotations/Example_v2.plan.json
```

Omitting `--execute` performs a dry run. `--write-plan` is optional; the default
replaces the annotation file's final suffix with `.plan.json`. Plan generation
refuses to overwrite an existing file. Use a new output name when replanning.
`--write-plan` and `--plan-file` are mutually exclusive and require
`--annotations-file`.

Review **both** the plan and the annotations file. The plan records an annotation
hash, not a duplicate of the annotation values. It contains:

- Format version, plan ID (SHA-256), dataset ID, workflow, and execution options.
- Explicit `annotate`, `version_staging`, `version_local`, and `add` actions.
- Target/source IDs, intended names and destinations, and whether dataset version
  references will be refreshed.
- Dataset membership including pinned version numbers.
- Snapshots of dataset, affected files, staging sources, and release destination:
  etags, file handles, names, parents, versions, and annotation hashes.
- Resolved local paths and SHA-256 content hashes for local uploads.

The review command reads remote metadata and hashes local upload files. It does
not download staging file content or make Synapse mutations. Phase-1 name/content
extraction is separate and may download files when explicitly configured.

## 3. Check or execute the reviewed plan

Check it again, without writes:

```bash
mamba run -n amp-als python -m synapse_dataset_manager update \
  --dataset-id syn123 \
  --annotations-file annotations/Example_update_annotations.json \
  --release-folder syn789 --version-label v2 \
  --plan-file annotations/Example_v2.plan.json
```

Then execute with exactly the same inputs/options:

```bash
mamba run -n amp-als python -m synapse_dataset_manager update \
  --dataset-id syn123 \
  --annotations-file annotations/Example_update_annotations.json \
  --release-folder syn789 --version-label v2 \
  --plan-file annotations/Example_v2.plan.json --execute
```

Remove `--write-plan` and `--dry-run` when executing. `--execute` without a reviewed
`--plan-file` fails. A plan is a review artifact, **not** a source of implicit CLI
options: repeat the release folder, local directory, version settings, workflow,
and schema-validation choice, or use unchanged dataset configuration.
`--skip-validation` only skips annotation schema validation; it does not bypass
artifact checks, stale-state checks, or result verification, and its value is
bound into the plan.

Editing annotations or changing options after review invalidates the plan. Do
not edit a plan directly: regenerate and review it. The integrity hash detects
accidental edits; it is not a signature or authorization mechanism. Treat plans,
annotations, and execution reports as trusted, potentially sensitive artifacts.

## Preflight and stale-state checks

Before writing, the engine recompiles the plan from the supplied annotations and
current state and requires exact equality with the reviewed plan. Changes to
membership/version references, source or target metadata/annotations, dataset or
release etags, options, or local bytes invalidate it. Missing/unreadable entities
and fingerprints fail closed.

Preflight also rejects missing local files, case-insensitive local filename
collisions, staging/local source conflicts, reused staging sources, staging
sources that are also update targets, missing release destinations for additions,
non-file targets, and release filename collisions. It never silently chooses a
new target when an artifact is stale.

During execution, all upload content is prepared **before the first remote
write**. Staging downloads are pinned to reviewed Synapse versions and checked
against reviewed file-handle IDs. Local files are copied to a private temporary
directory and their hashes checked, so uploads use the reviewed bytes rather than
a subsequently edited original. Full stale checks run again after this potentially
long step; target/source snapshots are also checked immediately before each action.
Temporary upload copies are removed after the run.

The stale-state baseline begins at **plan generation**, not phase-1 template
generation. Review annotation choices against the desired release before creating
a plan; this does not prove that old templates still express your intended metadata.

## Execution and verification

Actions run in deterministic target-ID order and stop at the first failure.
Versioned uploads and label-driven versions refresh the dataset's pinned reference
to the resulting file version, replacing old references for that file. Additions
are moved/renamed, annotated, and added at their resulting version. Existing files
keep their parents; specifying a release folder does not move every dataset file.

Verification checks names, intended parents, requested labels, required version
increments, intended annotation values, and dataset membership/version references.
A final dataset reference check preserves unmodified members. It does not claim a
full remote byte-for-byte integrity audit. Duplicate-label errors are failures,
not silently successful skips.

## Failure reports and recovery

Execution writes `<plan-file>.results.json` before the first mutation and updates
it atomically between actions. It records the plan ID and per-action states:
`not_started`, `applying`, `verifying`, `verified`, or `failed_or_partial`.
The overall status is `in_progress`, `complete`, or `incomplete`. Verified actions
also record their observed entity state. The engine checks that this state remains
stable during verification and through the final dataset reference check.

An API failure, verification failure, or handled interruption yields a nonzero
exit and an incomplete report. A hard kill may leave `in_progress`; treat an
`applying` action as potentially partially applied. A plan with an existing report
cannot silently be replayed, even if an earlier attempt failed before finishing.

Inspect Synapse and the report, repair or acknowledge partial changes, and prepare
fresh annotations/plan for the remaining desired work. **Do not delete a report
and blindly retry.** Replanning is explicit recovery, not automatic rollback or
idempotent resume.

These checks are not a distributed transaction or lock. Concurrent writers can
still race an API call after its last check, and remote failures can leave partial
mutations. Use a single release writer. No permissions simulation or custom
pre/post execution hook API is implemented yet; those remain separate extensions.
