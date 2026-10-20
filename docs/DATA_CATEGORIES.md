# Dataset data categories and Sankey classification

## Purpose

`dataCategory` is a multivalued dataset annotation that rolls granular `dataType` and `assessmentTypes` values into stable categories. It supports the portal dataset-collection Sankey:

```text
Dataset name -> granular data type or assessment type -> data category
```

`dataCategory` is intentionally distinct from `dataType`:

- `dataType` records the controlled, specific content, artifact, result, or modality represented by a dataset.
- `assessmentTypes` records the controlled instrument, test, or procedure represented by a dataset.
- `dataCategory` is the broader category assigned from either field.

For example, a clinical dataset with `dataType: adverse_events` and `assessmentTypes: ALSFRS-R` receives `Safety` and `Clinical Outcome` data categories.

## Annotation convention

Keep established broad/modality data types for compatibility with existing Synapse portal conventions, and add granular values alongside them when known:

```yaml
dataType:
  - transcriptomics
  - gene_expression
  - transcript_counts
dataCategory:
  - Transcriptomics
```

Do not put instruments into `dataType` merely for the Sankey. Keep them in `assessmentTypes`:

```yaml
dataType:
  - clinical
  - clinical_assessment
assessmentTypes:
  - ALSFRS-R
dataCategory:
  - Clinical Outcome
```

## Controlled categories

The `DataCategoryEnum` is defined once in
[`modules/shared/data-categories.yaml`](../modules/shared/data-categories.yaml) and is inherited by every dataset schema through `BaseDataset`.

It includes clinical categories (for example, `Safety` and `Clinical Outcome`), molecular categories (for example, `Genomics` and `Transcriptomics`), and cross-domain categories (for example, `Biomarker`, `Speech / Communication`, and `Digital Health`).

## Crosswalk and Sankey roles

[`mapping/data_categories.yaml`](../mapping/data_categories.yaml) is the authoritative, schema-qualified crosswalk. It records both the category derivation and each value's Sankey role:

| Role | Annotation behavior | Sankey behavior |
|---|---|---|
| `broad` | Retain as a compatibility/modality `dataType` value. | Exclude from middle nodes. |
| `granular` | Retain and use to derive `dataCategory`. | Include as a typed middle node. |
| `technical` | Retain supporting/processing metadata. | Exclude from middle nodes. |

The Sankey notebook is maintained separately. It should namespace middle nodes by source field so labels cannot collide, for example `Data Type: motor_assessment` and `Assessment Type: motor_assessment`.

A dataset with only a broad value such as `transcriptomics` can receive `dataCategory: Transcriptomics`, but must be reported as **Needs Granular Classification** because it has no granular Sankey middle node. A generic `clinical` value alone cannot identify a clinical category and must likewise be flagged.

`raw_sequencing` and `aligned_reads` are Sankey-included granular values. Their category must be inferred from a co-occurring modality data type (such as `genomics` or `transcriptomics`) or other trustworthy assay metadata. If that context is absent, flag the dataset for review.

## Governance

Derive `dataCategory` from the crosswalk by default. If a dataset requires an exception, record it in a versioned override artifact used by the annotation workflow; do not silently diverge from the crosswalk. Update the crosswalk whenever a mapped data type or assessment type is added or changed.
