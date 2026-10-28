# Dataset manager packaging and update redesign

## Goal and rollout

Make `update` a conservative general-purpose workflow. Select custom workflows
explicitly from a directory of reusable implementations. Package the tool here
before extracting it into its own repository. Do not change the LinkML model.

Implementation proceeds in independently reviewable stages:

1. **Package foundation (implemented):** move the current script into
   `synapse_dataset_manager/cli.py`; retain the root CLI wrapper; provide
   `python -m synapse_dataset_manager`; preserve command behavior and resource
   resolution. Add offline entry-point regression tests.
2. **Characterization and extraction (execution implemented):** shared Synapse
   execution in `operations.py`, orchestration in `engine.py`, and versioned JSON
   plan/result contracts in `plans.py`. Configuration extraction remains pending.
3. **Generic preparation (implemented baseline):** configurable dictionary grouping,
   file identity manifests, conservative matching, and reviewable action plans.
4. **Content identity and enrichment (partial):** configurable file-column name
   extraction implemented; independently selectable content/count enrichment pending.
5. **Custom workflows (partial):** ALL ALS identity/matching moved into `all_als.py`,
   explicitly selected; `general` is default. A broader custom hook API is pending.
6. **Reliable apply (implemented baseline):** preflight, stale-plan checks,
   checkpointed action outcomes, verification gates, and legacy artifact planning.
   No transaction, automatic rollback, or resumable execution is claimed.
7. **Repository extraction (pending):** move tool-specific source, tests, docs,
   and packaging metadata after resource boundaries are explicit.

Stage 1 did not change update policies. The subsequent policy increment now
implements explicit `general`/`all_als` selection, conservative general matching,
CSV identity manifests, file-column naming, configurable dictionary columns and
exact `_groups` enrichment. It also prevents overlapping staging/local uploads,
requires release folders for additions before mutations, and gates success on
operation/verification results. See QUICK_REFERENCE.md section 17 for the actual
supported configuration (flat snake_case keys under `update`).

Phase-2 execution now uses the shared engine and operations adapter; obsolete
batch execution helpers have been removed from `cli.py`. Dry runs compile reviewed
JSON plans from edited annotations. Apply requires `--plan-file`, binds all inputs
and options, compares remote snapshots/membership and local hashes, prepares pinned
content, and rechecks before writing. Reports checkpoint partial progress and block
silent replay. Dataset references are refreshed to resulting versions. See
[Reviewed Update Plans](REVIEWED_UPDATE_PLANS.md) for the implemented contract.

Phase-1 orchestration and shared legacy enrichment helpers remain in the CLI.
Characterization coverage is incremental, not complete. An arbitrary hook loader,
transactional rollback, and automatic resume are not implemented.

The nested configuration examples below describe the original design proposal,
not the current CLI/config contract. Generic dictionary fields currently use the
legacy global field mapping format: conflicting group-specific definitions are
rejected, and coded-value dictionary layouts remain future work.

## Target architecture

```text
synapse_dataset_manager/
  __init__.py
  __main__.py
  cli.py
  config.py
  updates/
    engine.py
    plans.py                 # Implemented JSON plan/result contract
    models.py                # Optional future typed domain objects
    matching.py
    dictionaries.py
    validation.py
    operations.py
    workflows/
      general.py
      all_als.py
```

Unrelated commands may remain in `cli.py` initially. A future `pyproject.toml`
will expose `synapse-dataset-manager`; do not claim installability until dependency
versions, optional extras, and package resources have been audited.

## Generic identities and dictionary grouping

Keep three concepts separate: source file identity, dictionary group, and release
filename. None requires a `viewName` annotation or a `Form Name` column.

Proposed configuration:

```yaml
update:
  workflow: general
  dictionary:
    path: metadata/data_dictionary.csv
    group_column: table_id
    field_column: variable_name
  file_identity:
    provider: manifest
    path: metadata/export_index.csv
    source_column: export_file
    name_column: display_name
    dictionary_group_column: table_id
```

A missing dictionary group column means an ungrouped dictionary, not an inferred
ALL ALS layout. Other dictionary columns can be configured explicitly.

An identity manifest is separate from annotation-value `.dict` mappings. Its
canonical columns are `source_filename` (or `source_synapse_id`), optional
`target_synapse_id`, `release_filename`, and `dictionary_group`. Source selectors
must resolve uniquely. Missing targets permit normal matching; an explicit
`add` action can force addition subject to collision checks.

Alternatively `file_identity.provider: file_column` reads a configured column
from each source data file. Require exactly one distinct nonempty value; retain
the original extension by default. A separate index file is handled by the
manifest provider. Conflicting manifest/extracted values are errors. Default
identity uses filenames without downloading content.

## Matching and annotations

Default matching order:

1. Explicit target ID (validate membership and source/target identity).
2. Source ID already in the dataset.
3. Exact release filename.
4. Explicitly configured normalization, if enabled.

No default fuzzy matching or view-name fallback. Ambiguous matches and multiple
sources targeting one entity block preparation. Unmatched incoming files propose
additions; absent existing files remain untouched. Renames must be explicit plan
actions, not incidental side effects of matching.

Keep dictionary enrichment, unique-column extraction, counts, migrations, and
new-file defaults independently configurable. Preserve existing annotation values
by default; fill missing values from staging metadata/defaults; support explicit
overrides. Do not take shared values from an arbitrary first file. Configured
inheritance requires consistency across the relevant files.

## Prepare, review, apply

Preparation writes annotations and an update plan. Record source/target IDs,
actions, match evidence, destinations, versions, validation issues, and source and
target state sufficient for stale-plan checks. The editable annotations and plan
must agree before execution.

Application performs shared and custom preflight checks, executes approved
actions, and verifies their results. Report partial completion and return a
nonzero status for failed actions or failed verification. Never report success
merely because the orchestration reached its last step. Prevent overlapping local
and staging uploads for the same target. Define dry-run reads/downloads explicitly.
Legacy `_staging_id` artifacts require an adapter and the same preflight checks.

Custom workflows provide identity/enrichment policies, plan validation, pre-apply
checks, and post-apply checks. The engine owns mutations, dry runs, and reporting.
Select workflow via explicit CLI override, then dataset config, then `general`.
Initially load registered modules only, not arbitrary Python paths from input
artifacts. ALL ALS owns form extraction, view interpretation, dictionary filtering,
and release-specific checks. Fuzzy suggestions must be reviewable.

## Stage 1 resource/dependency audit

The original script has no `__file__`-based paths or `sys.path` modifications.
Moving it does not require changing working-directory semantics:

- `Config` defaults `BASE_DIR` to the working directory, with schemas under
  `json-schemas`, output under `annotations`, migrations under
  `configs/field_migrations.yaml`.
- Configuration autodiscovery uses working-directory `config.yaml`; users can
  pass `-c configs/config.yaml` explicitly.
- Generated mapping paths and user-provided paths remain working-directory
  relative. Do not silently make them package-relative in this stage.
- Current path construction strips leading dots/slashes from configured directory
  values. Audit/fix absolute-path handling separately before repository extraction.
- Required imports: PyYAML, synapseclient, jsonschema. Conditional integrations:
  openpyxl, somadata, synapseutils; subprocess integrations also need auditing.
- No in-repository Python imports of the old module were found. The root wrapper
  preserves command invocation, not an undocumented Python helper API.

Before extraction, classify bundled defaults, external schemas, user/project
inputs, and outputs. Consume schemas through explicit paths or versioned model
artifacts; never create a second hand-maintained model source. Keep credentials,
private dataset configs, and generated outputs out of the new package/repository.

## Verification

Run all Python commands through `mamba run -n amp-als`. Stage 1 compares legacy
help before/after the move and tests root/module help parity, package imports,
working-directory configuration, and shared interrupt/error handling without
Synapse access. Later stages need mocked tests for duplicate identities, ambiguous
matches, dictionary grouping, extraction failures, annotation precedence, stale
plans, partial failures, dry runs, and custom workflow selection.

Run offline verification with `mamba run -n amp-als python -m unittest discover
-s tests -v`. Coverage includes package entry points, identity selection, manifest
errors, exact matching, ALL ALS disambiguation, dictionary groups, generated phase-1
artifacts, plan review/replay, local/remote stale state, pinned content preparation,
preflight mutation prevention, reference refresh, and partial/verification failures.
No live Synapse updates were performed.

Any new command/flag or user-facing behavior must be documented in
`docs/QUICK_REFERENCE.md` alongside implementation.
