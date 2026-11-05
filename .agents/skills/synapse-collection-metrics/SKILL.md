---
name: synapse-collection-metrics
description: Pull current dataset, participant, study, cohort, study-type, and cohort-type metrics from Synapse DatasetCollection syn66496326. Use when asked for ALS Knowledge Portal collection metrics, updated collection counts, or deduplicated study/cohort composition.
compatibility: Requires Synapse authentication and the amp-als mamba environment.
---

# Synapse collection metrics

Run the bundled script from the repository root:

```bash
mamba run -n amp-als python .agents/skills/synapse-collection-metrics/scripts/pull_metrics.py
```

The script reads the current (HEAD) annotations of the entities in `syn66496326`; it does not use local source or annotation files.

## Reporting rules

- Report **31 dataset entities** separately from the deduplicated dataset/study-family count.
- `participant_count` is a sum of per-dataset values, **not a count of unique people**. State both the sum and the number of datasets with a populated value; do not claim it is deduplicated without subject-level identifiers.
- The script's default conservative deduplication keeps the two TDP-43 assay datasets separate, because they have distinct GEO studies. Its confirmed related-dataset groups are encoded in `scripts/pull_metrics.py`.
- Explain that `cohort_count` and `study_count` are summed per entity in the raw result; use the deduplicated result for questions about underlying studies/cohorts.
- Type composition counts are **deduplicated dataset-family tags**. A multi-valued type contributes to every applicable type, so category totals need not equal the family or study total.
- Include the timestamp printed by the script when the user asks for “updated” or “current” metrics.

If the user supplies a different collection ID, run the script with `--collection-id SYNID`. Do not add a new deduplication group based only on a similar title: confirm that the datasets represent the same study/cohort first.
