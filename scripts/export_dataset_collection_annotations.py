#!/usr/bin/env python3
"""Export dataset-level annotation templates for every Dataset in a DatasetCollection.

This reads only Synapse entity metadata/annotations/wiki text. It does not download
Dataset contents or File entities.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import synapseclient
from synapseclient.models import DatasetCollection


def load_schema(schema_dir: Path, dataset_type: str) -> dict[str, Any]:
    path = schema_dir / f"{dataset_type}.json"
    with path.open() as f:
        return json.load(f)


def empty_value(prop: dict[str, Any]) -> Any:
    typ = prop.get("type")
    if typ == "array":
        return [""]
    if typ == "boolean":
        return False
    if typ in {"integer", "number"}:
        return None
    return ""


def create_template(schema: dict[str, Any], dataset_type: str) -> dict[str, Any]:
    out = {k: empty_value(v) for k, v in schema.get("properties", {}).items()}
    out["_dataset_type"] = dataset_type
    out["_schema_source"] = str(schema.get("$id", "json-schema"))
    out["_created_timestamp"] = datetime.now(timezone.utc).isoformat()
    return out


def ann_to_plain(ann: Any) -> dict[str, Any]:
    # syn.get_annotations returns an Annotations object/dict-like with metadata keys.
    out = {}
    for k, v in dict(ann).items():
        if k in {"id", "etag", "creationDate", "createdBy", "modifiedOn", "modifiedBy"}:
            continue
        out[k] = v
    return out


def is_filled(v: Any) -> bool:
    return v not in (None, "", [], [""])


def merge_existing(template: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    merged = dict(template)
    for k, v in existing.items():
        if is_filled(v):
            merged[k] = v
    return merged


def classify_dataset(name: str, annotations: dict[str, Any]) -> str:
    keys = set(annotations)
    omic_keys = {"assay", "platform", "libraryStrategy", "processingLevel", "sampleType", "tissue", "cellType"}
    clinical_keys = {"studyDesign", "assessmentTypes", "visitSchedule", "primaryOutcome", "clinicalDomain"}
    if keys & omic_keys:
        return "OmicDataset"
    if keys & clinical_keys:
        return "ClinicalDataset"
    lname = name.lower()
    if any(tok in lname for tok in ["rna", "atac", "chip", "methyl", "tdp", "cortex", "neuron", "glia", "genome", "metabolome", "epigenome"]):
        return "OmicDataset"
    return "ClinicalDataset"


def get_wiki_markdown(syn: synapseclient.Synapse, entity_id: str) -> list[dict[str, str]]:
    pages = []
    try:
        headers = syn.getWikiHeaders(entity_id)
    except Exception as e:
        return [{"error": str(e)}]
    for h in headers or []:
        wid = h.get("id") if isinstance(h, dict) else getattr(h, "id", None)
        title = h.get("title") if isinstance(h, dict) else getattr(h, "title", "")
        try:
            wiki = syn.getWiki(entity_id, wid)
            pages.append({"id": str(wid), "title": title or "", "markdown": getattr(wiki, "markdown", "") or wiki.get("markdown", "")})
        except Exception as e:
            pages.append({"id": str(wid), "title": title or "", "error": str(e)})
    return pages


def find_pub_hints(text: str) -> list[str]:
    hints = []
    patterns = [r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", r"PMID[:\s]*(\d+)", r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", r"doi\.org/([^\s)]+)"]
    for pat in patterns:
        for m in re.finditer(pat, text, flags=re.I):
            hints.append(m.group(0))
    return sorted(set(hints))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--collection-id", default="syn66496326")
    ap.add_argument("--schema-dir", default="json-schemas")
    ap.add_argument("--out-dir", default="annotations/dataset_collection_update")
    args = ap.parse_args()

    schema_dir = Path(args.schema_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    syn = synapseclient.Synapse()
    syn.login(silent=True)
    coll = DatasetCollection(id=args.collection_id).get()
    items = getattr(coll, "items", []) or []

    manifest = []
    all_templates = {}
    for item in items:
        ds_id = getattr(item, "entity_id", None) or getattr(item, "id", None) or str(item)
        ent = syn.get(ds_id, downloadFile=False)
        existing = ann_to_plain(syn.get_annotations(ds_id))
        ds_type = classify_dataset(ent.name, existing)
        schema = load_schema(schema_dir, ds_type)
        template = create_template(schema, ds_type)
        merged = merge_existing(template, existing)
        missing = [k for k in schema.get("properties", {}) if not is_filled(existing.get(k))]
        wiki_pages = get_wiki_markdown(syn, ds_id)
        wiki_text = "\n\n".join(p.get("markdown", "") for p in wiki_pages)
        pub_hints = find_pub_hints(wiki_text + "\n" + json.dumps(existing))

        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", ent.name).strip("_")[:100]
        record = {
            "synId": ds_id,
            "name": ent.name,
            "dataset_type": ds_type,
            "current_annotations": existing,
            "merged_annotation_template": merged,
            "missing_fields": missing,
            "wiki_pages": wiki_pages,
            "publication_hints": pub_hints,
        }
        with (out_dir / f"{safe}_{ds_id}.json").open("w") as f:
            json.dump(record, f, indent=2, sort_keys=True)
        all_templates[ds_id] = {ent.name: merged}
        manifest.append({
            "synId": ds_id,
            "name": ent.name,
            "dataset_type": ds_type,
            "missing_count": len(missing),
            "missing_fields": missing,
            "publication_hints": pub_hints,
        })

    with (out_dir / "all_dataset_annotation_templates.json").open("w") as f:
        json.dump(all_templates, f, indent=2, sort_keys=True)
    with (out_dir / "manifest.json").open("w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    print(f"Exported {len(manifest)} datasets to {out_dir}")
    for row in manifest:
        print(f"{row['synId']}\t{row['dataset_type']}\tmissing={row['missing_count']}\t{row['name']}")


if __name__ == "__main__":
    main()
