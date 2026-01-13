"""Merge regenerated ALL ALS annotations with the vetted backup content.

This script keeps the current Synapse IDs in annotations/all_als/*.json but
replaces each record's metadata with the data stored in
annotations/all_als_backup/*.json. Records are matched using the combination of
title and alternateName (or viewName when alternateName is missing). If multiple
backup entries share the same title, the script falls back to comparing
recordCount values before using the first match.

Usage:
    python scripts/merge_all_als_annotations.py

Run from the repository root so the relative paths resolve correctly.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
ANNOT_DIR = ROOT / "annotations" / "all_als"
BACKUP_DIR = ROOT / "annotations" / "all_als_backup"


def load_json(path: Path) -> Any:
    with path.open() as fh:
        return json.load(fh)


def dump_json(path: Path, payload: Any) -> None:
    with path.open("w") as fh:
        json.dump(payload, fh, indent=2)


def normalize_scalar(value: Any) -> Any:
    if isinstance(value, list):
        for item in value:
            if item not in (None, ""):
                return item
        return value[0] if value else ""
    return value


def normalize_bool(value: Any) -> bool:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, bool):
                return item
            if isinstance(item, str) and item.strip().lower() in {"true", "1", "yes"}:
                return True
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return False


def build_lookups(backup: Dict[str, Dict[str, Dict[str, Any]]]) -> Tuple[
    Dict[Tuple[str, str], Dict[str, Any]],
    Dict[Tuple[str, str], Dict[str, Any]],
    Dict[str, List[Dict[str, Any]]],
]:
    by_alt: Dict[Tuple[str, str], Dict[str, Any]] = {}
    by_view: Dict[Tuple[str, str], Dict[str, Any]] = {}
    by_title: Dict[str, List[Dict[str, Any]]] = {}

    for entry in backup.values():
        for title, meta in entry.items():
            meta_copy = deepcopy(meta)
            alt = meta_copy.get("alternateName") or ""
            if alt:
                by_alt[(title, alt)] = meta_copy

            view = meta_copy.get("viewName") or []
            if isinstance(view, list):
                for v in view:
                    if v:
                        by_view[(title, v)] = meta_copy

            by_title.setdefault(title, []).append(meta_copy)

    return by_alt, by_view, by_title


def merge_file_annotations(current_path: Path, backup_path: Path) -> None:
    current = load_json(current_path)
    backup = load_json(backup_path)
    by_alt, by_view, by_title = build_lookups(backup)

    unmatched: List[Tuple[str, str, Any]] = []
    merged: Dict[str, Dict[str, Dict[str, Any]]] = {}

    for syn, entry in current.items():
        merged_entry: Dict[str, Dict[str, Any]] = {}
        for title, meta in entry.items():
            alt = meta.get("alternateName") or ""
            candidate = by_alt.get((title, alt)) if alt else None

            if not candidate:
                views = meta.get("viewName") or []
                if isinstance(views, list):
                    for view in views:
                        candidate = by_view.get((title, view))
                        if candidate:
                            break

            if not candidate:
                candidates = by_title.get(title, [])
                if len(candidates) == 1:
                    candidate = candidates[0]
                elif len(candidates) > 1:
                    current_rc = meta.get("recordCount")
                    current_rc = (
                        current_rc[0]
                        if isinstance(current_rc, list) and current_rc
                        else current_rc
                    )
                    for cand in candidates:
                        rc = cand.get("recordCount")
                        rc = rc[0] if isinstance(rc, list) and rc else rc
                        if rc is not None and rc == current_rc:
                            candidate = cand
                            break
                    if not candidate:
                        candidate = candidates[0]

            if candidate is None:
                unmatched.append((title, alt, meta.get("viewName")))
                candidate = meta
            else:
                candidate = deepcopy(candidate)

            candidate["disease"] = normalize_scalar(candidate.get("disease"))
            candidate["studyPhase"] = normalize_scalar(candidate.get("studyPhase"))
            candidate["hasLongitudinalData"] = normalize_bool(
                candidate.get("hasLongitudinalData")
            )

            merged_entry[title] = candidate

        merged[syn] = merged_entry

    if unmatched:
        print(
            f"{current_path}: {len(unmatched)} entries lacked a backup match;"
            " kept regenerated content."
        )
        print("Examples:", unmatched[:5])

    dump_json(current_path, merged)


def replace_dataset_annotations(current_path: Path, backup_path: Path) -> None:
    dump_json(Path(current_path), load_json(Path(backup_path)))


def main() -> None:
    merge_file_annotations(
        ANNOT_DIR / "assess_file_annotations.json",
        BACKUP_DIR / "assess_file_annotations.json",
    )
    merge_file_annotations(
        ANNOT_DIR / "prevent_file_annotations.json",
        BACKUP_DIR / "prevent_file_annotations.json",
    )
    replace_dataset_annotations(
        ANNOT_DIR / "assess_dataset_annotations.json",
        BACKUP_DIR / "assess_dataset_annotations.json",
    )
    replace_dataset_annotations(
        ANNOT_DIR / "prevent_dataset_annotations.json",
        BACKUP_DIR / "prevent_dataset_annotations.json",
    )


if __name__ == "__main__":
    main()
