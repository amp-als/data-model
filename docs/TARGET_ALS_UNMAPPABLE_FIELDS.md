# Target ALS Unmappable Fields Documentation

This document catalogs Target ALS metadata fields that **cannot be mapped** to the current data model schemas and require new entity schemas in future phases.

## Overview

The Target ALS dataset contains comprehensive clinical, biospecimen, omics, and longitudinal data. While basic subject demographics, disease classification, and file-level metadata can be mapped to existing schemas, several important data categories require dedicated entity models.

**Current Status**: As of the initial mapping implementation, approximately **40-50%** of Target ALS columns are mappable to existing schemas (Subject, OmicFile). The remaining ~50-60% require new schemas documented below.

---

## 1. Clinical Assessments

### 1.1 ALSFRS-R (ALS Functional Rating Scale - Revised)

**Fields**: 14 fields total
- `alsfrs_r_subscore_1` through `alsfrs_r_subscore_9` (bulbar, fine motor, gross motor functions)
- `alsfrs_r_subscore_r1` through `alsfrs_r_subscore_r3` (respiratory subscores)
- `alsfrs_r_score_total` (total score, range 0-48)

**Why Unmappable**: These represent structured clinical assessment instruments collected at multiple timepoints per subject. They require:
- Temporal association (date/visit of assessment)
- Individual item scores and total scores
- Score interpretation/normalization

**Recommended Schema**: `ALSFRSAssessment` entity
- Links to Subject via `globalSubjectId`
- Assessment date/timepoint
- All subscores as individual fields
- Total score with validation (0-48 range)

**Priority**: **HIGH** - ALSFRS-R is the gold standard for tracking ALS disease progression

---

### 1.2 Cognitive Assessments

**Fields**:
- `ecas_score` (Edinburgh Cognitive and Behavioural ALS Screen)
- `als_cbs_score` (ALS Cognitive Behavioral Screen)

**Why Unmappable**: Cognitive assessment scores are:
- Timepoint-specific measurements
- Different scoring scales per instrument
- Not intrinsic subject attributes

**Recommended Schema**: `CognitiveAssessment` entity
- Links to Subject
- Assessment type (ECAS, ALS-CBS)
- Assessment date
- Raw score
- Interpretation (normal/impaired based on cutoffs)

**Priority**: **MEDIUM** - Important for phenotyping cognitive/behavioral impairment in ALS

---

### 1.3 Spirometry/Pulmonary Function Tests

**Fields**: ~40 fields including:
- Test parameters: `spirometry_test_type`, `spirometry_test_position`
- Trial data: `spirometry_test_trial_1_result_in_l`, `spirometry_test_trial_1_pcnt_predict` (repeated for trials 2-3)
- Derived metrics: FVC (Forced Vital Capacity), FEV1 (Forced Expiratory Volume), FEV1/FVC ratio
- Quality metrics: `spirometry_test_pcnt_variability`, effort completion flags
- Detailed spirometry: `fvc_l`, `fvc_pred`, `fvc_percent_pred`, `fvc_zvalue`, `fvc_lln`
- FEV1 metrics: `fev1_l`, `fev1_pred`, `fev1_percent_pred`, `fev1_zvalue`, `fev1_lln`
- Additional measurements: `pef_time_ms`, `pef_l_per_s`, `pif_l_per_s`, `fev6_l`, `fef2575_l_per_s`
- QC: `fvc_letter_grade`, `fev1_letter_grade`, `breath_maneuver_quality`, `acceptable`, `repeatable`

**Why Unmappable**: Spirometry data is:
- Multi-trial measurement protocol (need to track best of 3 trials)
- Complex derived values with normative predictions
- Quality control flags per measurement
- Longitudinal (repeated at each visit)

**Recommended Schema**: `PulmonaryFunctionTest` entity (extended)
- Links to Subject and Visit
- Test type, position, date
- Per-trial raw values
- Best trial derived metrics (FVC, FEV1, ratios)
- Predicted values, z-scores, lower limit of normal
- QC flags and repeatability

**Priority**: **HIGH** - Respiratory function is critical ALS outcome measure

---

## 2. Digital Health Tracking / Speech Metrics

**Fields**: ~30 fields across multiple domains

### Session Metadata
- `dht_administration_site` (clinic location)
- `session_id`, `session_number` (longitudinal tracking)
- `local_date_time`, `location` (At Home vs In Clinic)
- `series_id`, `series_number`, `effort_number` (nested session structure)

### Measurement QC
- `measurement_status` (Error vs Successful)
- `error_reason` (audio quality, participant issues, exclusions)
- `metric_domain` (FT = fine motor/speech)
- `metric_category` (Speech Metrics)
- `measurement_type` (Aggregate)

### Speech Acoustic Features (~20 metrics)

**Sentence Reading**:
- `sentence_reading_mean_sentence_speaking_rate_in_syll_per_s`
- `sentence_reading_mean_sent_articulation_rate_in_syll_per_s`
- `sentence_reading_mean_sent_articulation_precision_ratio`
- `sentence_reading_mean_sentence_pause_rate_ratio`
- `sentence_reading_mean_fixed_sent_voicing_regulation_ratio`
- `sentence_reading_min_sentence_monotonicity_in_hz`

**Sustained Phonation**:
- `sustained_phonation_mean_phonation_total_dur_pauseless_in_s`
- `sustained_phonation_mean_phonation_breathiness_in_db`
- `sustained_phonation_min_phonation_pitch_instability_in_hz`

**Category Naming (Verbal Fluency)**:
- `category_naming_mean_category_naming_pause_rate_ratio`
- `category_naming_mean_cat_naming_verbal_fluency_item_count`

**Object Recall (Memory)**:
- `object_recall_mean_object_recall_score_object_count`

**Story Recall (Memory)**:
- `story_recall_mean_immediate_story_recall_score_ratio`
- `story_recall_delayed_mean_delayed_story_recall_score_ratio`

**Picture Description (Spontaneous Speech)**:
- `picture_description_mean_image_descr_total_duration_in_s`
- `picture_description_mean_spontaneous_volition_1_word_count`
- `picture_description_mean_spont_vocabulary_variety_a_ratio`
- `picture_description_mean_spontaneous_lexical_density_ratio`
- `picture_description_mean_spontaneous_dbpi_density_ratio`
- `picture_description_mean_image_descr_sem_relevance_ratio`

**Why Unmappable**: Digital health data requires:
- Hierarchical session structure (subject → series → session → effort)
- Multi-domain metrics from different speech tasks
- QC status and error tracking
- Acoustic feature extraction methodology
- Home vs clinic administration context

**Recommended Schema**: `DigitalHealthAssessment` or `SpeechAssessment` entity
- Links to Subject and Visit
- Session metadata (site, location, datetime)
- QC status and error codes
- Per-task speech metrics grouped by domain
- Aggregate vs individual effort tracking

**Priority**: **MEDIUM-HIGH** - Novel digital biomarkers for bulbar function

---

## 3. Treatments/Medications

**Fields**:
- `taking_edaravone` (Yes/No/PEN)
- `taking_riluzole` (Yes/No/PEN)
- `taking_tofersen` (Yes/No/PEN - SOD1-targeted therapy)
- `coenrollment_clinical_trial_during_tals` (Yes/No/PEN)

**Why Unmappable**: Treatment data is:
- Timepoint-specific (medication status changes over time)
- Binary at snapshot but needs start/stop dates
- Dosage, duration, and response not captured in current fields
- Clinical trial co-enrollment affects data interpretation

**Recommended Schema**: `MedicationHistory` or `TreatmentRecord` entity
- Links to Subject and Visit
- Medication name (edaravone, riluzole, tofersen, etc.)
- Status (taking/not taking/pending)
- Start date, end date (if available in future data releases)
- Clinical trial co-enrollment flag

**Priority**: **MEDIUM** - Important confounder for analyses; needed for treatment-response studies

---

## 4. Biomarkers

**Fields**:
- `nfl_concentration_pg_per_ml` (Neurofilament Light Chain concentration in plasma/CSF)

**Why Unmappable**: Biomarker measurements are:
- Quantitative assay results (not subject attributes)
- Linked to specific biospecimens
- Timepoint-specific
- Assay methodology and batch effects important

**Recommended Schema**: `BiomarkerMeasurement` entity
- Links to Subject, Visit, and Biospecimen
- Biomarker type (NfL, pNfH, etc.)
- Concentration value + units
- Sample type (plasma, CSF, serum)
- Assay platform/vendor
- Collection date

**Priority**: **HIGH** - NfL is a leading prognostic biomarker in ALS

---

## 5. Detailed Genetic Data

### 5.1 Repeat Expansion Data

**Fields**:
- `c9orf72_repeat_size` (e.g., "2/10", "2/700+")
- `atxn2_repeat_size` (e.g., "22/23")
- `c9orf72_pathogenic_repeat_expansion` (Positive/Negative)
- `atxn2_pathogenic_repeat_expansion` (Positive/Negative)

**Why Unmappable**: Genetic variant data requires:
- Allele-specific repeat counts (diploid notation "allele1/allele2")
- Pathogenicity interpretation (normal vs intermediate vs pathogenic)
- Gene-specific thresholds (C9orf72 >30 repeats, ATXN2 >27 repeats)
- Assay methodology (PCR, repeat-primed PCR, Southern blot)

**Recommended Schema**: `GeneticVariant` entity
- Links to Subject
- Gene name (C9orf72, ATXN2)
- Variant type (repeat expansion, SNV, indel)
- Allele 1 value, Allele 2 value
- Pathogenicity classification
- Assay method

**Priority**: **HIGH** - Genotype-phenotype correlations are core research questions

---

### 5.2 Genetic QC Metrics

**Fields**:
- `sex_genotype` (XX/XY from genetic data)
- `sex_from_genotype` (Male/Female inferred from genotype)

**Why Unmappable**: These are QC validation fields comparing:
- Self-reported sex vs genetic sex
- Discrepancies indicate sample swaps or mislabeling

**Recommended Action**: Include in `GeneticQC` metadata or as flags in Subject schema
- Current approach: Can add `sexGenotype` field to Subject if needed

**Priority**: **LOW** - QC use only; sample concordance checks

---

## 6. Proteomics Assay Data

**Olink Proximity Extension Assay (PEA) Data**

**Fields**: ~25 fields for proteomics characterization

### Sample/Plate Metadata
- `sample_type` (Sample, Negative Control, Plate Control, Sample Control)
- `plate_id` (Plate 1, Plate 2)
- `well_id` (well position)

### Protein Identifiers
- `olink_id` (Olink assay identifier)
- `uniprot` (UniProt accession)
- `assay` (protein/antibody name)

### Assay Parameters
- `assay_type` (Assay vs Control)
- `panel` (Explore HT)
- `block` (1-8, technical plate sections)

### Measurement Values
- `count` (raw counts)
- `ext_npx` (extension NPX - internal control normalized)
- `intensity_normalized_npx` (intensity-normalized NPX)
- `pc_normalized_npx` (plate control normalized NPX)

### Quality Control Metrics
- `intra_cv` (intra-assay coefficient of variation)
- `inter_cv` (inter-assay coefficient of variation)
- `assay_qc` (Pass/Warning)
- `assay_qc_warn` (warning count: 0/1/2)
- `sample_qc` (Pass)
- `sample_block_qc_warn` (0/1)
- `sample_block_qc_fail` (0/1)
- `block_qc_fail` (0/1)

**Why Unmappable**: Proteomics data is:
- High-dimensional (3000+ proteins per sample)
- Plate-based assay with batch effects
- Multiple normalization levels (internal, intensity, plate control)
- Complex QC flags at assay and sample levels
- Requires linking to specific biospecimen aliquots

**Recommended Schema**: `ProteomicsAssay` or `OlinkAssay` entity
- Links to Subject, Biospecimen, Batch/Plate
- Protein identifier (Olink ID, UniProt)
- Assay panel and block
- Raw and normalized NPX values
- QC metrics (CVs, flags)
- Well position for spatial batch effects

**Priority**: **MEDIUM-HIGH** - Large-scale proteomics is a major Target ALS dataset component

---

## 7. Sequencing QC Metrics

**Fields**:
- `din` (DNA Integrity Number: 8.9-9.8)
- `gqn10`, `gqn30` (Genotype Quality Metrics at GQ≥10, GQ≥30 thresholds)
- `a260_280`, `a260_230` (Spectrophotometric purity ratios)

**Why Unmappable**: These are biospecimen/library-level QC metrics:
- Measured on DNA sample before sequencing
- Indicate sample quality and purity
- Used for inclusion/exclusion decisions
- Not file-level attributes (measured pre-sequencing)

**Recommended Schema**: Extend `Biospecimen` entity or create `SequencingQC` entity
- Links to Biospecimen
- DNA integrity (DIN score)
- Purity metrics (A260/280, A260/230)
- Genotyping QC (GQN10, GQN30)

**Priority**: **LOW-MEDIUM** - Important for data QC but not primary research variables

---

## 8. Administrative/Temporal Metadata

### File System Metadata
- `ingestion_date` (date added to Target ALS database)
- `file_update_time` (last file modification time)
- `file_size` (file size in bytes)

**Why Unmappable**: These are database/filesystem metadata, not biological metadata
- Captured by Synapse file metadata automatically
- Not needed in data model annotations

**Recommended Action**: No action needed - Synapse handles this natively

**Priority**: **N/A** - Already handled by platform

---

### Longitudinal Session Tracking
- `series_id` (unique series identifier)
- `series_number` (1, 2, 3... sequential visit number)
- `effort_number` (0-13, multiple measurement attempts per visit)

**Why Unmappable**: Requires formal `Visit` or `Session` entity to model:
- Hierarchical structure: Subject → Visit → Session → Measurement
- Visit numbering and sequencing
- Effort/attempt tracking within visits

**Recommended Schema**: `Visit` or `Session` entity
- Links to Subject
- Visit number/ID
- Visit date
- Visit type (baseline, follow-up)
- Related assessments/measurements

**Priority**: **MEDIUM** - Needed for longitudinal analyses

---

## 9. Additional Spirometry Metadata (Home Spirometry Device)

**Fields**:
- `coached` (Yes/No - was subject coached during test)
- `firmware_version` (4, 4.5, 4.8 - device firmware)
- `effort_rejected` (Yes/No/N/A - was effort rejected by QC)
- `series_comments` (free text comments)

**Why Unmappable**: Home spirometry device-specific metadata
- Device version tracking important for longitudinal consistency
- Coaching affects test validity
- Needs to be linked to Visit/Session entity

**Recommended Action**: Include in `PulmonaryFunctionTest` entity as optional fields

**Priority**: **LOW** - Useful metadata but not critical for most analyses

---

## Summary Statistics

| **Data Category** | **Field Count** | **Priority** | **Recommended Schema** |
|-------------------|-----------------|--------------|------------------------|
| ALSFRS-R Assessments | 14 | HIGH | `ALSFRSAssessment` |
| Cognitive Assessments | 2 | MEDIUM | `CognitiveAssessment` |
| Spirometry | ~40 | HIGH | `PulmonaryFunctionTest` |
| Digital Health/Speech | ~30 | MEDIUM-HIGH | `DigitalHealthAssessment` |
| Treatments/Medications | 4 | MEDIUM | `MedicationHistory` |
| Biomarkers | 1 | HIGH | `BiomarkerMeasurement` |
| Genetic Variants | 4 | HIGH | `GeneticVariant` |
| Genetic QC | 2 | LOW | Subject extension or `GeneticQC` |
| Proteomics Assay | ~25 | MEDIUM-HIGH | `OlinkAssay` |
| Sequencing QC | 5 | LOW-MEDIUM | Biospecimen extension or `SequencingQC` |
| Admin/Temporal | 3 | N/A | Platform-native |
| Longitudinal Session | 3 | MEDIUM | `Visit` / `Session` |
| Device Metadata | 4 | LOW | Part of `PulmonaryFunctionTest` |

**Total Unmappable Fields**: ~137 out of ~260 total Target ALS columns (~53%)

---

## Next Phase Priorities

### Phase 4: High-Priority Schema Design
1. **`ALSFRSAssessment`** - Core ALS outcome measure
2. **`PulmonaryFunctionTest`** - Respiratory function (survival predictor)
3. **`BiomarkerMeasurement`** - NfL and future biomarkers
4. **`GeneticVariant`** - Genotype-phenotype correlations

### Phase 5: Medium-Priority Schemas
5. **`DigitalHealthAssessment`** - Novel digital biomarkers
6. **`OlinkAssay`** - Large-scale proteomics data
7. **`MedicationHistory`** - Treatment tracking
8. **`Visit` / `Session`** - Longitudinal data structure

### Phase 6: Extensions
9. **`CognitiveAssessment`** - Cognitive phenotyping
10. Biospecimen/Sequencing QC extensions

---

## Implementation Notes

- All new entities should link to `Subject` via `globalSubjectId`
- Temporal entities need `visitDate` or `assessmentDate` fields
- QC flags should be boolean or enum types
- Numeric measurements need units explicitly defined
- Consider data type validation (ranges, allowed values)
- Plan for multi-timepoint aggregation queries

---

**Document Version**: 1.0
**Last Updated**: 2026-03-11
**Author**: Data Model Implementation - Target ALS Mapping Phase 1
