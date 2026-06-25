# Data Modeling Rules

**These rules are mandatory whenever you add, edit, or remove an attribute, enum,
slot, class, or mixin in the LinkML data model (`modules/**`).** They exist to keep
the model DRY, internally consistent, and correctly buildable. Read the whole file
before changing the model.

The source of truth is `modules/**`. Everything under `json-schemas/`, `dist/`, and
`ALS.jsonld` is **generated** — never hand-edit it.

---

## 1. Golden rule: define everything exactly once

Every class, enum, slot, and mixin must have **one** canonical definition in **one**
file. Do not copy a definition into a second file "to make a build work."

- Before adding any `enums:` / `classes:` / `slots:` entry, search the repo:
  `grep -rn "MyEnumName" modules/`. If it already exists, **reference it**, don't redefine it.
- Name collisions are silently dangerous: the full-model build (`dist/ALS.yaml`) globs
  every module and **deep-merges** same-named definitions, while the per-schema builds
  pick only a hand-listed subset of files. So two definitions with the same name can
  diverge per schema and still "build." This is exactly how `dataType`,
  `AssessmentTypeEnum`, and `LibraryStrategyEnum` drifted historically.

## 2. One concept per file for enums

Enums shared across more than one class live in their own dedicated file, e.g.:

| Enum | Canonical file |
|---|---|
| `OmicDataTypeEnum` | `modules/omics/data-types.yaml` |
| `ClinicalDataTypeEnum` | `modules/clinical/data-types.yaml` |
| `AssessmentTypeEnum` | `modules/clinical/assessment-types.yaml` |
| `LibraryStrategyEnum` | `modules/omics/library-strategy.yaml` |
| `StudyDesignEnum` | `modules/clinical/study-design.yaml` |

Do not define enums inline inside a dataset/file class module. If you remove the last
enum from a class module, delete the `enums:` key entirely (leave a comment) — never
leave an empty/`null` `enums:` mapping.

## 3. Dataset-level and file-level MUST share the same enum

When the same concept exists at both dataset and file level (e.g. `dataType`,
`fileFormat`, `assessmentType`/`assessmentTypes`, `libraryStrategy`), both classes must
resolve to the **same** canonical enum. Never give them two same-named-but-different
definitions. If the vocabularies legitimately differ, give them **distinctly named**
enums — do not reuse one name for two value sets.

When unifying or widening an enum, make it a **superset** so no existing annotation
value is invalidated. Check real usage first:
`grep -rho "the_value" annotations/ | sort | uniq -c`.

## 4. The Makefile uses hand-picked file lists — keep them in sync

Each per-schema target in the `Makefile` (`Dataset`, `ClinicalDataset`, `OmicDataset`,
`File`, `ClinicalFile`, `OmicFile`) merges an **explicit list** of module files
(`relevant_enums.yaml` + a list passed to `yq ea`). It is NOT a glob.

- If you create a new enum/slot file, you **must** add it to **every** target whose
  classes reference it. If you forget, the range resolves to nothing and the field is
  silently emitted as an **unconstrained string** (this is how `OmicFile.libraryStrategy`
  lost its enum). Always verify the enum is present after building (see §8).
- A class and its file/dataset counterpart often need the same enum file added to
  **both** their targets.
- The full-model targets (`dist/ALS.yaml`, `ALS.jsonld`) auto-discover files via
  `find modules`, so new files are picked up there automatically — but that does NOT
  cover the per-schema targets.

## 5. Slots vs inline attributes

- Reusable, cross-class fields belong in `modules/shared/props.yaml` as `slots:`, or in
  a shared mixin. Class-local one-off fields may stay as inline `attributes:`.
- **Any slot referenced by a class via `slots:` must have `in_subset: [portal]`.** The
  per-schema build filters `props.yaml` to portal-subset slots only
  (`relevant_props.yaml`); a referenced slot without the portal subset is dropped and
  the reference dangles.
- Prefer `mixins:` to share a coherent group of fields across classes (e.g. common omic
  file/dataset fields) rather than duplicating inline attributes in each class.

## 6. Field type / multivalued changes

- `multivalued: true` → the field is an **array** in the JSON Schema; otherwise it is a
  **scalar**. Changing this changes generated templates and how annotation values must
  be shaped. When you flip it, update affected annotation files accordingly (arrays vs
  scalars), and prefer a lossless conversion.
- `range:` must point at a real type or a single canonical enum. A `pattern:` on a
  string range must be intentional and as loose as the data standard requires
  (e.g. `dataset_code` was relaxed from a C-Path-only regex to `^[a-z0-9_]+$`).

## 7. Naming conventions

- Classes & mixins: `PascalCase` (`BaseDataset`, `OmicFile`, `OmicFileMixin`).
- Enums: `PascalCase` ending in `Enum` (`OmicDataTypeEnum`).
- Slots / attributes: keep existing casing of the field they represent; be descriptive
  and stable (renames ripple into annotations downstream).
- YAML: 2-space indentation; keep LinkML fields explicit (`title`, `description`,
  `range`, `required`, `multivalued`).

## 8. Always build and verify after a change

Run builds through the project env (`mamba run -n amp-als ...`). After editing the model:

```bash
# Rebuild only the schemas affected by your change (faster), e.g.:
mamba run -n amp-als make OmicDataset OmicFile

# Or rebuild everything:
mamba run -n amp-als make -B all
```

Then verify:

1. **Build succeeds** with no errors for every affected target.
2. **No duplicate definitions** remain: `grep -rn "MyName" modules/` returns one defining file.
3. **Dataset/file enum parity**: for a shared concept, the enum in
   `json-schemas/<X>Dataset.json` and `json-schemas/<X>File.json` is identical.
4. **Range is constrained**: the field you touched actually has its `enum` (not a bare
   string) in the generated JSON Schema.
5. If annotation files are affected, re-validate them against the rebuilt schema.

## 9. Removing things safely

Before deleting a class/enum/file, prove it is unused or fully redundant:

- `grep -rn "Name" modules/` — confirm nothing references it (or only redundant copies do).
- For "is this file redundant?" decisions, build the merged model **with and without**
  the file and diff the resolved classes/enums to confirm nothing is lost (an attribute
  that looks unique may be covered by inheritance, e.g. `studyType` via `BaseDataset`).

## 10. Commit hygiene

- Keep the source edit, the regenerated `json-schemas/` artifacts, and any doc updates
  in the **same** change.
- Concise imperative commit summaries, prefixed `feat:` / `fix:` per repo history.

---

### Quick checklist for any model change

- [ ] Definition exists exactly once (searched first)
- [ ] Shared enums in a dedicated file; dataset & file share one enum
- [ ] New enum/slot file added to every relevant Makefile target
- [ ] Slots referenced by classes have `in_subset: [portal]`
- [ ] Rebuilt affected schemas via `mamba run -n amp-als make ...`
- [ ] Verified build, no duplicates, dataset/file parity, range constrained
- [ ] Updated/validated affected annotation files
- [ ] Did not hand-edit generated files
