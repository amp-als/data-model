# ALL ALS update preflight plan

## Goal

Add a mandatory ALL ALS-only preflight before phase-1 annotations or phase-2 plan
creation. Each staged tabular file must have a corresponding data-dictionary view,
match that view's substantive columns exactly, contain configured required columns,
and have no configured PHI/PII headers. Any failure stops the update before an
annotations file, reviewed update plan, upload, move, annotation mutation, or other
Synapse write is made.

This is a deterministic header-based gate. Semantic examination of values for PHI/
PII is explicitly deferred to a separate version-two design.

## Implementation status

Implemented: sparse/filled CSV/XLS/XLSX dictionary parsing, canonical header/view
normalization, exact dictionary coverage, default ignored/required columns, external
version-1 PHI/PII policy loading, grouped value-free failures, and phase-1 placement
before mapping/annotation output. The default policy is
`configs/phi_pii_columns.yaml`. No live Synapse validation has been performed.

Still deferred: friendly aliases, semantic value inspection, explicit non-tabular
exemptions, and a structured machine-readable preflight report.

## Scope and workflow boundary

The validator belongs in `synapse_dataset_manager/updates/workflows/all_als.py`.
The `general` workflow is unchanged. It runs after staging files and their ALL ALS
view names are resolved, but before annotation templates/mappings are generated.
The reviewed-plan engine remains responsible for phase-2 state validation and
execution; this preflight supplies only valid phase-1 output.

Validation applies to every staged file prepared for the release. Existing release
files absent from staging are not revalidated. Unsupported/non-tabular staging
files fail unless a future explicit exemption policy is added; there is no silent
skip.

## Dictionary normalization

The dictionary parser must accept both supported layouts:

```csv
View Name,Field,Description
v_ALLALS_AS_DEMOGRAPHICS,nihguid,NIH GUID
,,Sex at birth
```

and:

```csv
View Name,Field,Description
v_ALLALS_AS_DEMOGRAPHICS,nihguid,NIH GUID
v_ALLALS_AS_DEMOGRAPHICS,Sex at birth,Sex at birth
```

For sparse dictionaries, a row inherits the most recent nonempty view name. For
fully populated dictionaries, every row provides it. Normalize into a mapping of
one normalized view name to its original display name and normalized fields. Empty
view/field values, a field before any view in sparse form, duplicate fields in one
view, duplicate normalized view names, duplicate file headers, and unknown/missing
configured columns are failures. Do not silently overwrite or choose one.

Use one documented normalization function for comparisons: trim whitespace, remove
a UTF-8 BOM where applicable, case-fold, and normalize runs of spaces, hyphens, and
underscores to one underscore. Do not add fuzzy or semantic matching.

The ALL ALS view for a staged file is the raw staging filename stem, as currently
used by the ALL ALS policy. It must resolve to exactly one normalized dictionary
view. No view aliases are supported initially.

### Deferred: friendly view aliases

A later feature may allow human-readable aliases (for example `demographics`) to
resolve to canonical raw ALL ALS view names. It must use an explicit one-to-one
configuration map, reject duplicate/ambiguous aliases, appear in the reviewed plan,
and never use fuzzy matching. Until then, every view-specific configuration key
must be the exact raw staging view name (subject only to the deterministic
normalization above), e.g. `v_ALLALS_AS_DEMOGRAPHICS`.

## Required and ignored columns

The initial dataset configuration contract is:

```yaml
update:
  workflow: all_als
  all_als:
    dictionary:
      view_column: "View Name"
      field_column: "Field"
      ignored_file_columns:
        - Form Name
        - form_name
        - NeuroGUID
    required_columns:
      all_files:
        - NeuroGUID
        - NeuroSTAmP
      by_view:
        v_ALLALS_AS_DEMOGRAPHICS:
          - nihguid
    phi_pii_columns_file: configs/phi_pii_columns.yaml
```

`ignored_file_columns` are ignored **only** for file-to-dictionary equality. They
are still read, screened for PHI/PII, and can be required. Thus `NeuroGUID` is
excluded from dictionary coverage while still required in every file. `Form Name`
and `form_name` normalize to one configured technical column; retain both examples
for clarity but reject duplicate normalized configuration entries at validation
startup. Future dictionaries may include these fields; then configuration should
be changed deliberately rather than implicitly changing validation behavior.

For each file:

1. Read and normalize every header.
2. Run the PHI/PII header screen.
3. Require all `all_files` columns.
4. Require `by_view[canonical_view_name]` columns when configured.
5. Remove ignored technical columns from the file-header set only.
6. Require exact equality between the remaining file headers and dictionary fields
   for that view.

A column may not simultaneously be required and forbidden by the PHI/PII policy,
or ignored and forbidden. Such configuration conflicts fail closed before file
processing. Required columns must exist as headers even if ignored for dictionary
coverage.

## PHI/PII header policy

Use a required, version-controlled external YAML file:

```yaml
version: 1
forbidden_columns:
  - first_name
  - last_name
  - full_name
  - date_of_birth
  - dob
  - address
  - email
  - phone
  - medical_record_number
  - mrn
  - social_security_number
  - ssn
```

Version 1 compares only normalized header names; it never reads or logs file
values. A missing, malformed, unknown-version, or conflicting policy file fails
closed for `all_als`. Exact normalized matches fail. Do not provide a casual CLI
switch to disable this gate.

`NeuroGUID` and `NeuroSTAmP` must not be placed in the forbidden policy when they
are required. Any future exception mechanism must be explicit and reviewable, not
a broad allow-unknown bypass.

## Errors and artifacts

Aggregate failures by file/view and category, for example:

```text
ALL ALS preflight failed

v_ALLALS_AS_DEMOGRAPHICS.csv → v_ALLALS_AS_DEMOGRAPHICS
  Required columns missing: neurostamp
  Dictionary columns absent from file: sex_at_birth
  File columns absent from dictionary: enrollment_identifier
  Forbidden PHI/PII headers: "Date of Birth" → date_of_birth
```

Error reports may include file names, raw header names, normalized names, view
names, and policy terms. They must never include cell values. Preflight failure
must leave no annotations JSON, mapping output, plan, result report, upload, or
other remote mutation from that invocation.

## Implementation and tests

1. Add a small ALL ALS preflight module with dictionary parsing, header loading,
   normalization, policy loading, config validation, and structured violations.
2. Call it from `all_als.prepare()` before templates/mappings are emitted.
3. Add the default policy file under `configs/` and document its ownership/review.
4. Add config-template examples using canonical view-name keys.
5. Extend QUICK_REFERENCE when the user-facing flags/config become implemented.
6. Add offline tests for sparse and fully populated dictionaries, canonical view
   matching, missing/unknown views, extra/missing columns, ignored-vs-required
   behavior, global/per-view requirements, duplicate headers/definitions,
   forbidden variants, policy/config failures, and no-output/no-mutation behavior.
7. Validate on a controlled ALL ALS dry run before any execution.

No LinkML model changes are required for this work.
