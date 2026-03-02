# Repository Guidelines

## Project Structure & Module Organization
- `modules/` contains the source LinkML model. Key areas: `portal/` (top-level `Dataset`/`File`), `base/`, `mixins/`, `datasets/`, `entities/`, plus domain folders (`clinical/`, `omics/`, `reference/`, `shared/`, `governance/`).
- `dist/` and `ALS.jsonld` are generated build artifacts.
- `json-schemas/` holds generated JSON Schemas consumed downstream.
- `mapping/` contains JSONata mapping expressions (for example, `mapping/cpath.jsonata`).
- `scripts/` contains utility and model-management scripts; `notebooks/` is exploratory.

## Build, Test, and Development Commands
- `make all`: builds core artifacts (`ALS.jsonld`, `dist/ALS.yaml`, `dist/ALS.ttl`, `dist/ALS.toon`).
- `make Dataset` (or `make ClinicalDataset`, `make OmicFile`, etc.): generates specific JSON Schemas under `json-schemas/`.
- `make -B`: force full rebuild.
- `schematic schema convert ALS.jsonld`: validates generated JSON-LD with `schematic` (also used in CI).
- Prereqs used by repo/CI: `yq`, `jq`, `linkml` tools (`gen-json-schema`, `gen-rdf`), `json-dereference-cli`, `retold`.

## Coding Style & Naming Conventions
- YAML: 2-space indentation; keep LinkML fields explicit (`description`, `is_a`, `mixins`, enums).
- Python scripts: PEP 8, snake_case filenames, clear function names, minimal side effects.
- Schema class names use PascalCase (for example, `BaseDataset`, `ClinicalFile`); enums and slots should remain descriptive and stable.
- Keep source-of-truth edits in `modules/`; do not hand-edit generated files unless regenerating in same change.

## Testing Guidelines
- No large standalone unit-test suite is required today; validation is build-centric.
- Before PR: run `make -B`, regenerate affected schemas, and run `schematic schema convert ALS.jsonld`.
- For mapping changes, validate with representative input against the updated schema output.

## Commit & Pull Request Guidelines
- Follow existing commit style from history: concise, imperative summaries, commonly prefixed with `feat:` or `fix:`.
- Keep commits focused (schema change + regenerated artifacts + docs together when applicable).
- PRs should include: scope summary, impacted modules (for example `modules/clinical/*`), commands run, and any schema/artifact diffs reviewers should inspect.
- CI (`.github/workflows/main-ci.yml`) runs on PRs touching `modules/**`; ensure generated outputs are consistent before requesting review.
