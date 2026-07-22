#!/usr/bin/env python3
"""Build a human-review proposal for dataset-level annotation updates.

Inputs are the exported metadata-only JSON files from
scripts/export_dataset_collection_annotations.py. Output is a JSON annotation file
that can be reviewed before any Synapse annotation writes occur.
"""
from __future__ import annotations

import csv
import glob
import json
import re
from pathlib import Path
from typing import Any

IN_DIR = Path("annotations/dataset_collection_update")
OUT_JSON = IN_DIR / "proposed_dataset_annotation_updates.json"
OUT_CSV = IN_DIR / "proposed_dataset_annotation_updates.csv"

# Evidence-based cohort proposals from dataset names, existing annotations, and
# dataset wiki/publication hints exported from Synapse. study_count is the count
# of distinct studies represented by the Dataset entity; cohort_count is the
# number of reported biological/clinical cohorts or trial arms available at the
# dataset level.
COHORT_PROPOSALS: dict[str, dict[str, Any]] = {
    "syn67751280": {"cohortType": ["Disease-Only"], "cohort_count": 2, "study_count": 1, "rationale": "FTD/ALS postmortem TDP-43-negative nuclei cohorts in GSE126541; no explicit healthy-control annotation present."},
    "syn67748058": {"cohortType": ["Case-Control"], "cohort_count": 3, "study_count": 1, "rationale": "C9-ALS, C9-FTD, and control postmortem cortex cohorts in GSE219280/Nat Commun paper."},
    "syn67746133": {"cohortType": ["Case-Control"], "cohort_count": 3, "study_count": 1, "rationale": "C9-ALS, C9-FTD, and control postmortem cortex cohorts in GSE219279/Nat Commun paper."},
    "syn72016774": {"cohortType": ["Interventional-Treatment"], "cohort_count": 1, "study_count": 1, "rationale": "Trehalose expanded-access biomarker dataset; open-label non-randomized treatment cohort."},
    "syn67729513": {"cohortType": ["Case-Control"], "cohort_count": 6, "study_count": 1, "rationale": "Current disease annotations list ALS, FTD, Control, Pre-fALS, Parkinson's Disease, and Alzheimer's Disease cohorts."},
    "syn67719824": {"cohortType": ["Case-Control"], "cohort_count": 2, "study_count": 1, "rationale": "FTD-GRN and control human cerebral cortex cohorts in GSE163122/Nat Neurosci paper."},
    "syn72379204": {"cohortType": ["Interventional-Treatment", "Placebo-Control"], "cohort_count": 4, "study_count": 1, "rationale": "Phase 2 randomized dose-ranging trial: placebo plus 150, 300, and 450 mg reldesemtiv arms."},
    "syn73882344": {"cohortType": ["Interventional-Treatment", "Placebo-Control"], "cohort_count": 2, "study_count": 1, "rationale": "Randomized placebo-controlled topiramate trial: topiramate and placebo arms."},
    "syn72379205": {"cohortType": ["Interventional-Treatment", "Placebo-Control"], "cohort_count": 2, "study_count": 1, "rationale": "COURAGE-ALS Phase 3 randomized trial: reldesemtiv and placebo arms."},
    "syn67740891": {"cohortType": ["Case-Control"], "cohort_count": 2, "study_count": 1, "rationale": "Current disease annotations list ALS and Control cohorts for bulk H3K27ac ChIP-seq."},
    "syn72379206": {"cohortType": ["Registry"], "cohort_count": 1, "study_count": 1, "rationale": "ALS Analysis and Assessment Survey Study is a survey/registry-style observational dataset."},
    "syn67754663": {"cohortType": ["Disease-Only"], "cohort_count": 2, "study_count": 1, "rationale": "FTD/ALS postmortem TDP-43-negative nuclei RNA-seq cohorts in GSE126542; no explicit healthy-control annotation present."},
    "syn72379207": {"cohortType": ["Interventional-Treatment", "Placebo-Control"], "cohort_count": 2, "study_count": 1, "rationale": "Ceftriaxone ALS clinical trial: ceftriaxone and placebo/control arms."},
    "syn67737779": {"cohortType": ["Case-Control"], "cohort_count": 7, "study_count": 1, "rationale": "Current disease annotations list ALS, FTD, Control, Pre-fALS, Alzheimer's Disease, Other Neurological Disorders, and Other Motor Neuron Disease."},
    "syn72379208": {"cohortType": ["Interventional-Treatment", "Placebo-Control"], "cohort_count": 2, "study_count": 1, "rationale": "OMOP representation of the same ceftriaxone ALS clinical trial with treatment and placebo/control arms."},
    "syn73965826": {"cohortType": ["Case-Control", "Natural-History"], "cohort_count": 2, "study_count": 1, "rationale": "Target ALS GNHS natural-history dataset with ALS and control cohorts."},
    "syn67713129": {"cohortType": ["Case-Control"], "cohort_count": 2, "study_count": 1, "rationale": "Current disease annotations list ALS and Control cohorts in GSE115310."},
    "syn74483113": {"cohortType": ["Case-Control"], "cohort_count": 2, "study_count": 1, "rationale": "Title and annotations describe an ALS case/control cohort (dbGaP phs004288.v1.p1)."},
    "syn67743547": {"cohortType": ["Case-Control"], "cohort_count": 3, "study_count": 1, "rationale": "C9-ALS, C9-FTD, and control postmortem cortex cohorts in GSE219278/Nat Commun paper."},
    "syn69694463": {"cohortType": ["Case-Control", "Natural-History"], "cohort_count": 2, "study_count": 1, "rationale": "ASSESS ALL ALS prospective observational study enrolling symptomatic ALS and control participants."},
    "syn68932658": {"cohortType": ["Disease-Only"], "cohort_count": 1, "study_count": 1, "rationale": "ALS/FTD disease-model RNA methylation study; no explicit control cohort in current disease annotation."},
    "syn67733559": {"cohortType": ["Case-Control"], "cohort_count": 8, "study_count": 1, "rationale": "Current disease annotations list ALS, FTD, Control, Pre-fALS, Alzheimer's Disease, Parkinson's Disease, Other Neurological Disorders, and Other Motor Neuron Disease."},
    "syn69694420": {"cohortType": ["Interventional-Treatment"], "cohort_count": 1, "study_count": 1, "rationale": "Trehalose expanded-access protocol; open-label non-randomized treatment cohort."},
    "syn69694674": {"cohortType": ["At-Risk", "Healthy-Control", "Natural-History"], "cohort_count": 2, "study_count": 1, "rationale": "PREVENT ALL ALS prospective observational study enrolling at-risk individuals and controls."},
    "syn73686173": {"cohortType": ["Aggregate-Reference"], "cohort_count": 2, "study_count": 1, "rationale": "ALS Compute aggregate/reference dataset with ALS and FTD disease cohorts summarized at consortium level."},
}


def clean_dois(hints: list[str]) -> list[str]:
    dois = []
    for h in hints:
        s = h.strip().rstrip(").,;")
        s = re.sub(r"^doi\.org/", "", s, flags=re.I)
        if s.lower().startswith("10."):
            dois.append("doi:" + s)
    return sorted(set(dois))


def filled(v: Any) -> bool:
    return v not in (None, "", [], [""])


def main() -> None:
    updates = {}
    rows = []
    for path in sorted(glob.glob(str(IN_DIR / "*.json"))):
        p = Path(path)
        if p.name in {"manifest.json", "all_dataset_annotation_templates.json", OUT_JSON.name}:
            continue
        rec = json.load(open(p))
        ds_id = rec["synId"]
        name = rec["name"]
        merged = rec["merged_annotation_template"]
        proposal = dict(merged)
        changed_fields = []

        cp = COHORT_PROPOSALS[ds_id]
        for key in ["cohortType", "cohort_count", "study_count"]:
            if not filled(rec["current_annotations"].get(key)):
                proposal[key] = cp[key]
                changed_fields.append(key)

        # Fill citation from DOI hints only when citation is absent. Keep all DOI
        # hints for review; these may include method/data descriptor papers.
        if not filled(rec["current_annotations"].get("citation")):
            dois = clean_dois(rec.get("publication_hints", []))
            if dois:
                proposal["citation"] = dois
                changed_fields.append("citation")

        proposal["_review_status"] = "pending"
        proposal["_cohort_update_rationale"] = cp["rationale"]
        proposal["_changed_fields"] = changed_fields
        updates[ds_id] = {name: proposal}
        rows.append({
            "synId": ds_id,
            "name": name,
            "dataset_type": rec["dataset_type"],
            "cohortType": ";".join(cp["cohortType"]),
            "cohort_count": cp["cohort_count"],
            "study_count": cp["study_count"],
            "citation_added": ";".join(proposal.get("citation", [])) if "citation" in changed_fields else "",
            "changed_fields": ";".join(changed_fields),
            "rationale": cp["rationale"],
        })

    with OUT_JSON.open("w") as f:
        json.dump(updates, f, indent=2, sort_keys=True)
    with OUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_CSV}")


if __name__ == "__main__":
    main()
