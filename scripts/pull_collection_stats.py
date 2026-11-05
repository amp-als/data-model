#!/usr/bin/env python3
"""Pull participant counts, cohort stats, and study stats from DatasetCollection syn66496326.

Resolution order per field:
  1. Draft (HEAD) version of the dataset on Synapse — most up-to-date live annotations.
  2. proposed_dataset_annotation_deltas.json  — pending updates not yet pushed to Synapse.

Each value in the output is tagged [synapse] or [deltas] so you can see exactly where
it came from.
"""

import json
import os
from collections import defaultdict
from pathlib import Path

import synapseclient
from synapseclient.models import DatasetCollection

COLLECTION_ID = os.getenv("DATASETS_COLLECTION_ID", "syn66496326")
DELTAS_PATH = Path(__file__).resolve().parent.parent / (
    "annotations/dataset_collection_update/proposed_dataset_annotation_deltas.json"
)

# Fields resolved per-dataset with source tracking
STAT_FIELDS = ["participant_count", "cohort", "cohortType", "cohort_count", "study_count", "studyType"]


def _scalar(val):
    """Unwrap a single-element list to a scalar; return None for empty/blank."""
    if isinstance(val, list):
        return val[0] if len(val) == 1 else (val if val else None)
    return val if val not in ("", None) else None


def _to_list(val):
    """Normalise annotation value to a plain list of non-empty strings."""
    if val is None:
        return []
    if isinstance(val, list):
        return [str(v) for v in val if v not in ("", None)]
    s = str(val).strip()
    return [s] if s else []


def load_deltas(path: Path) -> dict:
    """Load proposed_dataset_annotation_deltas.json, keyed by synapse ID."""
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def resolve_fields(syn_id: str, syn_annos: dict, deltas: dict) -> dict:
    """
    Resolve each stat field with source tagging.

    Returns a dict:  field -> {"value": ..., "source": "synapse" | "deltas" | None}
    """
    # Pick the matching deltas entry (first inner value, ignoring _-prefixed keys)
    delta_entry: dict = {}
    if syn_id in deltas:
        inner = deltas[syn_id]
        # inner is {dataset_name: {field: value, ...}}
        if isinstance(inner, dict):
            for v in inner.values():
                if isinstance(v, dict):
                    delta_entry = v
                    break

    result = {}
    for field in STAT_FIELDS:
        syn_val = syn_annos.get(field)
        delta_val = delta_entry.get(field) if delta_entry else None

        # Determine effective value and source
        if field in ("cohort", "cohortType", "studyType"):
            syn_list = _to_list(syn_val)
            delta_list = _to_list(delta_val)
            if syn_list:
                result[field] = {"value": syn_list, "source": "synapse"}
            elif delta_list:
                result[field] = {"value": delta_list, "source": "deltas"}
            else:
                result[field] = {"value": [], "source": None}
        else:  # scalar fields
            s = _scalar(syn_val)
            d = _scalar(delta_val)
            if s is not None:
                result[field] = {"value": s, "source": "synapse"}
            elif d is not None:
                result[field] = {"value": d, "source": "deltas"}
            else:
                result[field] = {"value": None, "source": None}

    return result


def main():
    syn = synapseclient.Synapse()
    syn.login(silent=True)

    deltas = load_deltas(DELTAS_PATH)
    print(f"Loaded deltas for {len(deltas)} dataset(s) from {DELTAS_PATH.name}")

    print(f"\nFetching DatasetCollection: {COLLECTION_ID} (draft/HEAD versions)")
    collection = DatasetCollection(id=COLLECTION_ID).get()
    items = collection.items if hasattr(collection, "items") else []
    print(f"Found {len(items)} datasets\n")

    rows = []

    for item in items:
        # Use .id (string) not the full EntityRef object — gets draft/HEAD, not the pinned version
        item_id = item.id if hasattr(item, "id") else str(item)
        pinned_ver = item.version if hasattr(item, "version") else "?"

        try:
            entity = syn.get(item_id, downloadFile=False)
            name = entity.name
            syn_annos = dict(entity.annotations) if entity.annotations else {}
        except Exception as e:
            print(f"  WARNING: Could not fetch {item_id}: {e}")
            continue

        fields = resolve_fields(item_id, syn_annos, deltas)
        rows.append(
            {
                "id": item_id,
                "pinned_ver": pinned_ver,
                "name": name,
                **{f: fields[f]["value"] for f in STAT_FIELDS},
                **{f"_src_{f}": fields[f]["source"] for f in STAT_FIELDS},
            }
        )

    # ── Per-dataset table ──────────────────────────────────────────────────
    print("=" * 110)
    print("PER-DATASET STATS  (source: [S]=synapse draft  [D]=local deltas  [—]=missing)")
    print("=" * 110)
    print(
        f"{'Dataset':<55} {'SynID':<14} {'Pin':>4} {'Participants':>12} {'Cohorts':>7} {'Studies':>7}"
    )
    print("-" * 110)

    total_participants = 0
    datasets_with_counts = 0
    all_cohort_types: dict = defaultdict(int)
    all_study_types: dict = defaultdict(int)
    all_cohorts: set = set()

    SRC = {"synapse": "S", "deltas": "D", None: "—"}

    for r in rows:
        pc = r["participant_count"]
        cc = r["cohort_count"]
        sc = r["study_count"]
        display_name = r["name"][:53]

        def fmt(val, field):
            tag = SRC[r[f"_src_{field}"]]
            if val is None:
                return f"[{tag}]"
            return f"{val}[{tag}]"

        pc_str = fmt(pc, "participant_count")
        cc_str = fmt(cc, "cohort_count")
        sc_str = fmt(sc, "study_count")

        print(
            f"  {display_name:<53} {r['id']:<14} {r['pinned_ver']:>4} "
            f"{pc_str:>14} {cc_str:>9} {sc_str:>9}"
        )

        cohort_type = r["cohortType"]
        cohort = r["cohort"]
        study_type = r["studyType"]
        ct_src = SRC[r["_src_cohortType"]]
        c_src = SRC[r["_src_cohort"]]
        st_src = SRC[r["_src_studyType"]]

        if cohort_type:
            print(f"    cohortType [{ct_src}] : {', '.join(cohort_type)}")
        if cohort:
            print(f"    cohort     [{c_src}] : {', '.join(cohort)}")
        if study_type:
            print(f"    studyType  [{st_src}] : {', '.join(study_type)}")

        # Accumulate totals
        if pc is not None:
            try:
                total_participants += int(pc)
                datasets_with_counts += 1
            except (ValueError, TypeError):
                pass

        for ct in cohort_type:
            if ct:
                all_cohort_types[ct] += 1
        for st in study_type:
            if st:
                all_study_types[st] += 1
        for c in cohort:
            if c:
                all_cohorts.add(c)

    # ── Aggregate summary ─────────────────────────────────────────────────
    print(f"\n{'=' * 110}")
    print("AGGREGATE SUMMARY")
    print("=" * 110)
    print(f"\nDatasets in collection                    : {len(rows)}")
    print(f"Datasets with participant_count annotated : {datasets_with_counts}")
    print(f"Total participant_count (sum)             : {total_participants:,}")
    print(
        "\n  NOTE: datasets may share participants — this is a sum of per-dataset counts,\n"
        "        not necessarily unique individuals across the collection."
    )

    print(f"\n{'─' * 70}")
    print("COHORT STATS")
    print(f"{'─' * 70}")
    if all_cohort_types:
        print("cohortType values across collection:")
        for ct, count in sorted(all_cohort_types.items(), key=lambda x: -x[1]):
            print(f"  {ct:<45} appears in {count} dataset(s)")
    else:
        print("  No cohortType annotations found.")

    if all_cohorts:
        print(f"\nDistinct cohort labels ({len(all_cohorts)} unique):")
        for c in sorted(all_cohorts):
            print(f"  {c}")
    else:
        print("\n  No cohort annotations found.")

    print(f"\n{'─' * 70}")
    print("STUDY STATS")
    print(f"{'─' * 70}")
    if all_study_types:
        print("studyType values across collection:")
        for st, count in sorted(all_study_types.items(), key=lambda x: -x[1]):
            print(f"  {st:<45} appears in {count} dataset(s)")
    else:
        print("  No studyType annotations found.")

    # ── Coverage gaps ─────────────────────────────────────────────────────
    missing_pc = [r for r in rows if r["participant_count"] is None]
    missing_cohort = [r for r in rows if not r["cohortType"] and not r["cohort"]]
    missing_study = [r for r in rows if not r["studyType"]]

    if missing_pc:
        print(f"\n{'─' * 70}")
        print(f"Datasets missing participant_count in BOTH sources ({len(missing_pc)}):")
        for r in missing_pc:
            print(f"  {r['name'][:70]}  ({r['id']})")

    if missing_cohort:
        print(f"\n{'─' * 70}")
        print(f"Datasets missing cohort/cohortType in BOTH sources ({len(missing_cohort)}):")
        for r in missing_cohort:
            print(f"  {r['name'][:70]}  ({r['id']})")

    if missing_study:
        print(f"\n{'─' * 70}")
        print(f"Datasets missing studyType in BOTH sources ({len(missing_study)}):")
        for r in missing_study:
            print(f"  {r['name'][:70]}  ({r['id']})")


if __name__ == "__main__":
    main()
