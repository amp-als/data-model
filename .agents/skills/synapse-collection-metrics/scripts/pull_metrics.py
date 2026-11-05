#!/usr/bin/env python3
"""Report live, conservatively deduplicated metrics for a Synapse DatasetCollection."""

import argparse
from collections import Counter
from datetime import datetime, timezone

import synapseclient
from synapseclient.models import DatasetCollection

DEFAULT_COLLECTION_ID = "syn66496326"

# Each group is one underlying study/cohort represented by multiple dataset entities.
# Keep this list evidence-based. In particular, the two TDP-43 assay datasets are
# intentionally not grouped: they correspond to distinct GEO studies.
DEDUPLICATION_GROUPS = {
    "Divergent impacts of C9orf72 (multi-omics)": {
        "syn67748058", "syn67746133", "syn67740891", "syn67743547"
    },
    "ASSESS ALL ALS (clinical and speech)": {"syn69694463", "syn76965568"},
    "PREVENT ALL ALS (clinical and speech)": {"syn69694674", "syn76965569"},
    "Ceftriaxone trial (SDTM and OMOP)": {"syn72379207", "syn72379208"},
    "Trehalose expanded access (protocol and biomarker)": {"syn69694420", "syn72016774"},
}


def as_list(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)] if str(value).strip() else []


def scalar(value):
    values = as_list(value)
    return values[0] if values else None


def integer(value):
    value = scalar(value)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def family_rows(rows):
    """Return groups of rows, with ungrouped entities as one-row families."""
    by_id = {row["id"]: row for row in rows}
    assigned = set()
    families = []
    for label, ids in DEDUPLICATION_GROUPS.items():
        members = [by_id[entity_id] for entity_id in ids if entity_id in by_id]
        if len(members) > 1:
            families.append((label, members))
            assigned.update(row["id"] for row in members)
    for row in rows:
        if row["id"] not in assigned:
            families.append((row["name"], [row]))
    return families


def canonical_family_metrics(members):
    """Use the largest reported study/cohort count once per confirmed family."""
    def maximum(field):
        values = [row[field] for row in members if row[field] is not None]
        return max(values) if values else 0

    # Type annotations should be retained if present on any representation.
    study_types = set()
    cohort_types = set()
    for row in members:
        study_types.update(row["studyType"])
        cohort_types.update(row["cohortType"])
    return maximum("study_count"), maximum("cohort_count"), study_types, cohort_types


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection-id", default=DEFAULT_COLLECTION_ID)
    args = parser.parse_args()

    syn = synapseclient.Synapse()
    syn.login(silent=True)
    collection = DatasetCollection(id=args.collection_id).get()
    items = collection.items if hasattr(collection, "items") else []

    rows = []
    for item in items:
        entity_id = item.id if hasattr(item, "id") else str(item)
        entity = syn.get(entity_id, downloadFile=False)
        annotations = dict(entity.annotations or {})
        rows.append({
            "id": entity_id,
            "name": entity.name,
            "participant_count": integer(annotations.get("participant_count")),
            "cohort_count": integer(annotations.get("cohort_count")),
            "study_count": integer(annotations.get("study_count")),
            "cohortType": as_list(annotations.get("cohortType")),
            "studyType": as_list(annotations.get("studyType")),
        })

    raw_studies = sum(row["study_count"] or 0 for row in rows)
    raw_cohorts = sum(row["cohort_count"] or 0 for row in rows)
    participants = [row["participant_count"] for row in rows if row["participant_count"] is not None]

    families = family_rows(rows)
    dedup_studies = dedup_cohorts = 0
    study_types = Counter()
    cohort_types = Counter()
    for _, members in families:
        studies, cohorts, family_study_types, family_cohort_types = canonical_family_metrics(members)
        dedup_studies += studies
        dedup_cohorts += cohorts
        study_types.update(family_study_types)
        cohort_types.update(family_cohort_types)

    print(f"Retrieved (UTC): {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    print(f"Collection: {args.collection_id}")
    print()
    print("METRICS")
    print(f"Dataset entities: {len(rows)}")
    print(f"Underlying dataset/study families: {len(families)}")
    print(f"Participants (per-dataset sum): {sum(participants):,} ({len(participants)} datasets populated)")
    print(f"Studies: {dedup_studies} deduplicated ({raw_studies} raw per-entity sum)")
    print(f"Cohorts: {dedup_cohorts} deduplicated ({raw_cohorts} raw per-entity sum)")
    print()
    print("DEDUPLICATED STUDY TYPE COMPOSITION (family tags)")
    for value, count in study_types.most_common():
        print(f"{value}: {count}")
    print()
    print("DEDUPLICATED COHORT TYPE COMPOSITION (family tags)")
    for value, count in cohort_types.most_common():
        print(f"{value}: {count}")
    print()
    print("CONFIRMED DEDUPLICATION GROUPS")
    for label, members in families:
        if len(members) > 1:
            print(f"{label}: {', '.join(row['id'] for row in members)}")


if __name__ == "__main__":
    main()
