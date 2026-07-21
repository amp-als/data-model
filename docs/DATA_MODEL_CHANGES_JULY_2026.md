# Data Model Changes — July 2026

This document tracks all data model changes made during the week of July 7–9, 2026. Changes are organized by theme.

---

## 1. Enum Deduplication

### CellTypeEnum
- **Problem:** Defined in two places — `modules/entities/Biospecimen.yaml` and `modules/shared/common-enums.yaml` — with different, divergent value sets.
- **Fix:** Removed from `Biospecimen.yaml`. Merged both value sets into a single superset in `common-enums.yaml`.
- **Canonical location:** `modules/shared/common-enums.yaml`
- **Values added to superset:** `motor_neuron`, `neurons`, `NeuN+ neurons`, `astrocytes`, `astrocyte`, `microglia`, `oligodendrocyte lineage cells`, `oligodendrocyte`, `other glia`, `whole_blood`, `pbmc`, `fibroblasts`, `fibroblast`, `iPSC`, `primary_cell`, `immortalized_cell_line`, `stem_cell`, `differentiated_cell`, `organoid`, `unknown`, `other`

### CurationLevelEnum
- **Problem:** Defined in two places — `modules/governance/portals.yaml` (values: `Raw`, `Standardized`, `Non-Standardized`, `Unknown`) and `modules/shared/common-enums.yaml` (values: `tier1`, `tier2`, `tier3`, `unknown`). Both value sets were in use in annotations.
- **Fix:** Removed from `portals.yaml`. Merged into a superset in `common-enums.yaml`.
- **Canonical location:** `modules/shared/common-enums.yaml`

---

## 2. Attribute Consolidation: processingLevel → curationLevel

- **Problem:** `processingLevel` (`ProcessingLevelEnum`: `raw`, `processed`, `analyzed`, `integrated`) existed on `OmicDataset` and `OmicFile`, overlapping conceptually with `curationLevel` on `BaseDataset`.
- **Fix:**
  - Merged `ProcessingLevelEnum` values (`raw`, `processed`, `analyzed`, `integrated`) into `CurationLevelEnum`.
  - Removed `ProcessingLevelEnum` entirely from `common-enums.yaml`.
  - Removed `processingLevel` attribute from `OmicDataset` and `OmicFile`.
  - Added `curationLevel` to `BaseFile` so all file-level schemas inherit it.
  - Made `curationLevel` `multivalued: true` on both `BaseDataset` and `BaseFile`.
  - Updated `curationLevel` description from "TBD" to "Level of data processing and curation applied to this dataset/file."
- **Canonical location:** `modules/base/BaseDataset.yaml`, `modules/base/BaseFile.yaml`

---

## 3. dataFormat Removal

- **Problem:** `dataFormat` on `OmicDataset` had a broken `range: Data` (not a valid enum) and was never populated in annotations.
- **Fix:** Removed `dataFormat` entirely. `fileFormat` is the canonical field for file-level format information and already exists on file-level schemas.

---

## 4. collection → program Rename

- **Problem:** The `collection` attribute and `CollectionEnum` were ambiguously named, conflating research consortia with data repositories.
- **Fix:**
  - Renamed attribute `collection` → `program` in `modules/mixins/CommonMixins.yaml`.
  - Renamed `CollectionEnum` → `ProgramEnum` in `modules/governance/portals.yaml`.
  - Updated description: "Research consortium(s) or program(s) that produced or funded this resource."
- **Impact:** 10 annotation files using `collection` need to be updated to `program`.

---

## 5. source → originalRepository Rename

- **Problem:** The `source` attribute (`range: string`, required) was ambiguously named and unconstrained. `SourceNode` enum existed but was not wired to the attribute.
- **Fix:**
  - Renamed attribute `source` → `originalRepository` in `modules/mixins/CommonMixins.yaml`.
  - Renamed `SourceNode` → `OriginalRepositoryEnum` in `modules/governance/portals.yaml`.
  - Wired `originalRepository` to `range: OriginalRepositoryEnum`.
  - Updated description: "Repository or platform where this data was originally housed before ingestion into the AMP-ALS portal."
  - Added `dbGaP` and `Sequencing Read Archive` to `OriginalRepositoryEnum`.
- **Conceptual distinction:**
  - `program` = who produced/funded the data (consortium/initiative)
  - `originalRepository` = where the data was originally housed (Synapse, GEO, dbGaP, etc.)
- **Impact:** 8 annotation files using `source` need to be updated to `originalRepository`. Annotation values that are consortium names (`ALL ALS`, `Answer ALS`, `NEALS`) should migrate to `program`.

---

## 6. collectionDate Moved to File Level

- **Problem:** `collectionDate` was in `SpecimenTypeMixin`, which is included in `OmicDatasetMixin`, placing it at the dataset level. A single collection date is a specimen-level concept, not meaningful aggregated across a whole dataset.
- **Fix:** Removed `collectionDate` from `SpecimenTypeMixin` (`CommonMixins.yaml`). Added it directly to `OmicFileMixin` (`FileMixins.yaml`).
- **Result:** `collectionDate` now appears on file-level annotations only.

---

## 7. DiseaseEnum Additions

Added to `modules/shared/common-enums.yaml`:
- `Other Motor Neuron Disease` — motor neuron disease not otherwise classified as ALS, PLS, PMA, or PBP
- `Other Neurological Disorders` — neurological disorder not otherwise classified

---

## 8. DiseaseSubtypeEnum Additions

Added to `modules/shared/common-enums.yaml` (adjacent to their gene-name equivalents):
- `TDP43-ALS` — alternate notation for TARDBP-ALS
- `PROGRANULIN-ALS` — alternate notation for GRN-ALS
- `TAU-ALS` — alternate notation for MAPT-ALS

---

## 9. datePublished Type Fix

- **Problem:** `datePublished` on `BaseDataset` had `range: integer`, which is incorrect for a date field.
- **Fix:** Changed to `range: date` (ISO 8601 format, e.g. `2024-03-15`).
- **Note:** No annotations were using this field, so no annotation migration needed.

---

## 10. FunderEnum Created

- **Problem:** `funder` on `BaseDataset` was `range: string` with no controlled vocabulary.
- **Fix:** Created `FunderEnum` in `modules/governance/portals.yaml`. Updated `funder` to `range: FunderEnum`.
- **Values:** `NIH`, `NIA`, `NINDS`, `DoD`, `MDA`, `CZI`, `ERC`, `Target ALS`, `ALSA`, `Answer ALS`, `Penn Medicine`, `Other`
- **Convention:** Abbreviations used as keys; full names in descriptions.
- **Impact:** 1 annotation using `National Institutes of Health` needs updating to `NIH`.

---

## 11. includedInDataCatalog Removed

- **Problem:** `includedInDataCatalog` overlapped with `url` and `originalRepository`. Only 1 annotation used it (a dbGaP URL).
- **Fix:** Removed `includedInDataCatalog` from `CommonMixins.yaml`. Consolidated into `url`, which was made `multivalued: true` with an updated description covering both original location and external catalog links.

---

## 12. libraryStrategy Removed — Consolidated into assay

- **Problem:** `libraryStrategy` (`LibraryStrategyEnum`: `RNA_seq`, `WGS`, `WES`, `ChIP_seq`, `ATAC_seq`, `bisulfite_seq`, `amplicon_seq`, `targeted_seq`) was redundant with `assay` (`AssayEnum`). For sequencing data, the library strategy IS the assay — annotating both required duplicating the same information under different field names.
- **Fix:**
  - Removed `libraryStrategy` attribute from `OmicDataset` and `OmicFile`.
  - Removed `LibraryStrategyEnum` and deleted `modules/omics/library-strategy.yaml`.
  - `assay` is now the sole field capturing the measurement/sequencing strategy.
- **Impact:** 3 annotations using `libraryStrategy` need to migrate values to `assay`:
  - `RNA_seq` → `RNA-seq`
  - `WGS` → `whole genome sequencing`

---

## 13. `funder` Slot Divergence Fix

- **Problem:** `funder` had two conflicting definitions: `props.yaml` had `range: string` (unconstrained) while `BaseDataset` had `range: FunderEnum`. Both coexisted, violating the "define exactly once" rule.
- **Fix:**
  - Updated `props.yaml` `funder` slot: `range: string` → `range: FunderEnum`, added `multivalued: true` and `title: Funder`.
  - Removed inline `funder` attribute from `BaseDataset`; added `funder` to `BaseDataset.slots`.
- **Canonical location:** `modules/shared/props.yaml`

---

## 14. Slot Deduplication — Group 1 (Props.yaml vs Inline Conflicts)

- **Problem:** 15 fields existed in both `props.yaml` AND as inline `attributes:` in class/mixin files, violating the "define exactly once" rule. Most `props.yaml` definitions were missing `in_subset: [portal]` (making them filtered dead code in per-schema builds) and had stale `multivalued`/`required` values that diverged from the active inline definitions.
- **Affected fields:** `assay`, `fileFormat`, `libraryLayout`, `libraryPreparationMethod`, `assessmentType`, `clinicalDomain`, `administrationMode`, `studyPhase`, `keyMeasures`, `hasLongitudinalData`, `completenessLevel`, `title`, `description`, `creator`, `contributor`, `species`, `citation`
- **Fix:**
  - Added `in_subset: [portal]` and corrected `multivalued`/`required` for all 15 slots in `props.yaml`.
  - Removed the redundant inline `attributes:` definitions and replaced with `slots:` references in:
    - `CommonMetadataMixin` — `description`, `creator`, `contributor`, `species`, `citation`
    - `BaseDataset` — `title`
    - `OmicDatasetMixin` — `assay`, `libraryLayout`, `libraryPreparationMethod`
    - `ClinicalDatasetMixin` — `clinicalDomain`
    - `OmicFileMixin` — `assay`, `libraryLayout`, `libraryPreparationMethod`
    - `ClinicalFileMixin` — `clinicalDomain`, `studyPhase`
    - `OmicDataset` — `libraryPreparationMethod`
    - `OmicFile`, `ClinicalFile`, `SpeechFile` — `fileFormat`
    - `ClinicalFile` — `assessmentType`, `administrationMode`, `studyPhase`, `keyMeasures`, `hasLongitudinalData`, `completenessLevel`
- **Side fix:** `studyPhase` in `ClinicalFileMixin` had `range: string` (wrong). Corrected to `range: StudyPhaseEnum` by replacing the inline definition with the canonical slot.
- **Side fix:** `fileFormat` was unconstrained (plain string, no enum) in `OmicFile.json` and `ClinicalFile.json` because `file-formats.yaml` was not included in those Makefile targets. Now correctly constrained to `FileFormatEnum`.
- **Side fix:** `libraryPreparationMethod` was unconstrained in `OmicDataset.json` because `parameters.yaml` was missing from that Makefile target. Now correctly constrained.

---

## 15. New Canonical Slots — Group 2 (Inline-Only Fields Promoted)

- **Problem:** 8 fields were duplicated as inline `attributes:` across 2 or more classes but had no canonical slot definition in `props.yaml`, violating the DRY principle.
- **Fix:** Added 8 new slots to `props.yaml` with `in_subset: [portal]` and appropriate `range`/`multivalued` values. Removed all inline duplicate definitions and replaced with `slots:` references.

| Slot | Range | Multivalued | Removed from |
|---|---|---|---|
| `platform` | `PlatformEnum` | true | `OmicDataset`, `OmicFile` |
| `keywords` | `string` | true | `BaseDataset`, `BaseFile` |
| `curationLevel` | `CurationLevelEnum` | true | `BaseDataset`, `BaseFile` |
| `studyType` | `StudyLevelEnum` | true | `BaseDataset`, `ClinicalDatasetMixin`, `ClinicalFile` |
| `GEOSuperSeries` | `string` | false | `OmicDatasetMixin`, `OmicFileMixin` |
| `FACSPopulation` | `string` | true | `OmicDatasetMixin`, `OmicFileMixin` |
| `participant_count` | `integer` | false | `BaseDataset`, `ClinicalFile` |
| `alignmentMethod` | `AlignmentMethodEnum` | false | `OmicFile` class, `OmicFileMixin` |

- **Bug fix:** `participant_count` was incorrectly `multivalued: true` in `ClinicalFile`. Corrected to a scalar integer.
- **New pattern introduced:** `slot_usage` — used in `BaseDataset` to override `keywords: required: true` while the shared slot definition carries `required: false` (needed because file schemas use the same slot but don't require keywords). This is the first use of `slot_usage` in the model.
- **Canonical location for all 8 slots:** `modules/shared/props.yaml`

---

## 16. `dataType` Intra-Domain Redundancy Cleanup — Group 3

- **Problem:** `dataType` was defined with `range: Data` (a deprecated class) in both `ClinicalDatasetMixin` and `OmicDatasetMixin`. These mixin definitions were always overridden by the class-level domain-specific enum (`ClinicalDataTypeEnum`, `OmicDataTypeEnum`) when building specific schemas, but they also fed the generic `Dataset` union schema — producing the deprecated `Data` class (single value: `deprecated_use_domain_specific`) in `Dataset.json`.
- **Fix:**
  - Removed `dataType` inline attribute from `ClinicalDatasetMixin` and `OmicDatasetMixin`.
  - Added `slots: [dataType]` + `slot_usage: dataType: required: false` to `portal/Dataset.yaml` so the union schema retains the field via the canonical props.yaml slot.
  - Updated `dataType` slot in `props.yaml`: added `multivalued: true`, changed `required: true` → `required: false`.
- **Result:** Domain-specific schemas (`OmicDataset`, `ClinicalDataset`, `SpeechDataset`, etc.) still use their precise enum via class-level inline overrides. The `Dataset` union schema uses the generic `any_of: [Data, Metadata]` slot definition, which is appropriate for a catch-all schema.
- **Unchanged:** All class-level `dataType` inline overrides in `OmicDataset`, `OmicFile`, `ClinicalDataset`, `ClinicalFile`, `SpeechDataset`, `SpeechFile`, and `BaseFile` — these are intentional polymorphism, not redundancy.

---

## 17. Makefile Enum File Fixes

- **Problem:** Several per-schema Makefile targets were missing enum module files, causing fields to render as unconstrained strings in the generated JSON schemas despite having a `range:` in the YAML source.
- **Fixes applied:**

| Target | Change | Reason |
|---|---|---|
| `OmicDataset`, `OmicFile` | Removed `modules/omics/library-strategy.yaml` | File was deleted in a prior commit (`403ac72`) but Makefile was never updated; caused build failure |
| `OmicDataset` | Added `modules/omics/parameters.yaml` to `relevant_enums` | `LibraryPreparationMethodEnum` was unconstrained in `OmicDataset.json` |
| `OmicFile`, `ClinicalFile`, `File` | Added `modules/reference/file-formats.yaml` to `relevant_enums` | `FileFormatEnum` was unconstrained in `OmicFile.json` and `ClinicalFile.json` |
| `Dataset`, `File` | Added `modules/omics/platforms.yaml` to `relevant_enums` | `PlatformEnum` needed for `platform` slot in union schemas |
| `Dataset` | Added `modules/omics/parameters.yaml` to `relevant_enums` | `LibraryPreparationMethodEnum`, `AlignmentMethodEnum` needed for omic slots in union schema |
| `Dataset` | Added `modules/clinical/domains.yaml`, `modules/clinical/assessment-types.yaml` to temp merge | `ClinicalDomainEnum`, `AssessmentTypeEnum` needed for clinical slots in union schema |
| `File` | Added `modules/clinical/assessment-types.yaml`, `modules/entities/ClinicalAssessment.yaml` to temp merge | `AssessmentTypeEnum`, `StudyPhaseEnum`, `AdministrationModeEnum`, `CompletenessLevelEnum` needed for clinical file slots |

---

## Annotation Migration Summary

The following annotation fields need updating across existing annotation JSON files:

| Old field/value | New field/value | Files affected |
|---|---|---|
| `collection` | `program` | ~10 files |
| `source` (consortium values) | `program` | ~8 files |
| `source` (repository values) | `originalRepository` | ~8 files |
| `funder: "National Institutes of Health"` | `funder: "NIH"` | ~1 file |
| `includedInDataCatalog` | `url` | ~1 file |
| `curationLevel` (scalar) | `curationLevel` (array) | files using this field |
| `processingLevel` | `curationLevel` | files using this field |
| `libraryStrategy: "RNA_seq"` | `assay: "RNA-seq"` | ~3 files |
| `libraryStrategy: "WGS"` | `assay: "whole genome sequencing"` | ~3 files |
