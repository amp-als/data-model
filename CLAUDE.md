# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Data model changes — REQUIRED reading

**Whenever you add, edit, or remove any attribute, enum, slot, class, or mixin in the
LinkML data model (`modules/**`), you MUST read and follow
[`docs/DATA_MODELING_RULES.md`](docs/DATA_MODELING_RULES.md) — every time, without
exception.**

Non-negotiable highlights (the full rules live in that doc):

- **Define everything exactly once.** Search before adding (`grep -rn "Name" modules/`);
  reference existing definitions instead of duplicating them.
- The source of truth is `modules/**`. **Never hand-edit** generated files under
  `json-schemas/`, `dist/`, or `ALS.jsonld`.
- Dataset-level and file-level fields for the same concept **share one canonical enum**.
- The per-schema `Makefile` targets use **hand-picked file lists**, not globs — when you
  add a new enum/slot file, add it to every relevant target or the field is silently
  emitted unconstrained.
- **Always rebuild and verify** after a change (see §8 of the rules doc).

## Build environment

All build/CLI commands run through the `amp-als` env:

```bash
mamba run -n amp-als make <Target>     # e.g. OmicDataset, ClinicalFile, all
mamba run -n amp-als python synapse_dataset_manager.py <command> ...
```

## More repo guidance

See [`docs/AGENTS.md`](docs/AGENTS.md) for project structure, build/test commands, and
commit/PR conventions.
