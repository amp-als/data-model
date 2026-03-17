#!/usr/bin/env python3
"""Count participants in CSV, TSV, XLSX, and plain-text files.

Participant count = number of data rows (total rows minus header row).

With --id-column, counts unique values of that column across all files
instead of counting rows per file.

Optionally writes recordCount back to a file-annotations JSON file using
the CSV filename stem as the key matched against each entry's viewName field.
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


TABULAR_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls"}


def read_tabular(path: Path) -> pd.DataFrame | None:
    """Read a tabular file (CSV, TSV, XLSX) into a DataFrame."""
    try:
        ext = path.suffix.lower()
        if ext in (".xlsx", ".xls"):
            return pd.read_excel(path)
        elif ext == ".tsv":
            return pd.read_csv(path, sep="\t")
        else:
            return pd.read_csv(path)
    except Exception as e:
        print(f"WARNING: Could not read {path}: {e}", file=sys.stderr)
        return None


def count_file(path: Path) -> int | None:
    """Return the number of data rows in a file."""
    if not path.exists():
        print(f"WARNING: File not found: {path}", file=sys.stderr)
        return None
    if path.stat().st_size == 0:
        print(f"WARNING: {path} is empty, skipping.", file=sys.stderr)
        return None

    ext = path.suffix.lower()
    if ext in TABULAR_EXTENSIONS:
        df = read_tabular(path)
        return len(df) if df is not None else None
    else:
        # Plain text: count lines minus header
        try:
            total = sum(1 for _ in open(path, encoding="utf-8"))
            if total == 0:
                print(f"WARNING: {path} is empty, skipping.", file=sys.stderr)
                return None
            return total - 1
        except Exception as e:
            print(f"WARNING: Could not read {path}: {e}", file=sys.stderr)
            return None


def collect_files(directory: Path, recursive: bool) -> list[Path]:
    """Return all supported tabular and .txt files in a directory."""
    pattern = "**/*" if recursive else "*"
    files = []
    for ext in (*TABULAR_EXTENSIONS, ".txt"):
        files.extend(directory.glob(pattern + ext))
    return sorted(files)


def count_unique_participants(paths: list[Path], id_column: str) -> dict:
    """
    Count unique values of id_column across all files.

    Returns a dict with per-file counts and the combined unique count.
    """
    all_ids: set = set()
    per_file: list[tuple[str, int | None]] = []

    for path in paths:
        ext = path.suffix.lower()
        if ext in TABULAR_EXTENSIONS:
            df = read_tabular(path)
        else:
            try:
                df = pd.read_csv(path, sep=None, engine="python")
            except Exception as e:
                print(f"WARNING: Could not read {path}: {e}", file=sys.stderr)
                per_file.append((path.name, None))
                continue

        if df is None:
            per_file.append((path.name, None))
            continue

        if id_column not in df.columns:
            print(f"WARNING: Column '{id_column}' not found in {path.name}, skipping.", file=sys.stderr)
            per_file.append((path.name, None))
            continue

        ids = df[id_column].dropna().unique()
        per_file.append((path.name, len(ids)))
        all_ids.update(ids)

    return {"per_file": per_file, "unique_total": len(all_ids)}


def print_table(results: list[tuple[str, int | None]]) -> None:
    col1 = max((len(name) for name, _ in results), default=4)
    col1 = max(col1, len("File"))
    col2 = max(len("Participants"), 12)
    sep = f"{'─' * col1}  {'─' * col2}"

    header = f"{'File':<{col1}}  {'Participants':>{col2}}"
    print(header)
    print(sep)

    total = 0
    for name, count in results:
        if count is None:
            print(f"{name:<{col1}}  {'ERROR':>{col2}}")
        else:
            print(f"{name:<{col1}}  {count:>{col2}}")
            total += count

    print(sep)
    print(f"{'Total':<{col1}}  {total:>{col2}}")


def update_annotations(
    annotations_path: Path,
    counts: dict[str, int],
    field: str,
    dry_run: bool,
) -> None:
    """Write counts into ``field`` for matching entries in a file-annotations JSON.

    Matching: the CSV/TXT stem (e.g. ``v_ALLALS_AS_ASSEAELOG``) is compared
    against each annotation entry's ``viewName[0]`` value.
    """
    with open(annotations_path) as f:
        annotations = json.load(f)

    updated = 0
    for _syn_id, file_info in annotations.items():
        for _title, ann in file_info.items():
            view_names = ann.get("viewName") or []
            view_name = view_names[0] if view_names else None
            if view_name and view_name in counts:
                ann[field] = [counts[view_name]]
                updated += 1

    if dry_run:
        print(f"[dry-run] Would update {updated} entries in {annotations_path}")
    else:
        with open(annotations_path, "w") as f:
            json.dump(annotations, f, indent=2)
        print(f"Updated {updated} entries in {annotations_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Count participants (data rows) in CSV, TSV, XLSX, and TXT files."
    )
    parser.add_argument(
        "files",
        nargs="*",
        metavar="FILE",
        help="One or more file paths to process.",
    )
    parser.add_argument(
        "--dir",
        metavar="DIR",
        help="Directory to scan for .csv, .tsv, .xlsx, and .txt files.",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Scan --dir recursively.",
    )
    parser.add_argument(
        "--id-column",
        metavar="COLUMN",
        help=(
            "Column name to use as participant identifier. "
            "When set, counts unique values of this column across all files "
            "instead of counting rows per file."
        ),
    )
    parser.add_argument(
        "--update-annotations",
        metavar="ANNOTATIONS_JSON",
        help=(
            "Path to a file-annotations JSON file. "
            "Writes the row count into each matching entry's recordCount field "
            "(matched via viewName)."
        ),
    )
    parser.add_argument(
        "--field",
        default="recordCount",
        metavar="FIELD",
        help="Annotation field to update (default: recordCount).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without writing changes.",
    )
    args = parser.parse_args()

    paths: list[Path] = []

    if args.files:
        paths.extend(Path(f) for f in args.files)

    if args.dir:
        d = Path(args.dir)
        if not d.is_dir():
            print(f"ERROR: Not a directory: {d}", file=sys.stderr)
            sys.exit(1)
        paths.extend(collect_files(d, recursive=args.recursive))

    if not paths:
        parser.print_help()
        sys.exit(0)

    if args.id_column:
        result = count_unique_participants(paths, args.id_column)
        per_file = result["per_file"]
        unique_total = result["unique_total"]

        # Print per-file unique counts
        col1 = max((len(name) for name, _ in per_file), default=4)
        col1 = max(col1, len("File"))
        label = f"Unique {args.id_column}"
        col2 = max(len(label), 12)
        sep = f"{'─' * col1}  {'─' * col2}"

        print(f"{'File':<{col1}}  {label:>{col2}}")
        print(sep)
        for name, count in per_file:
            if count is None:
                print(f"{name:<{col1}}  {'ERROR':>{col2}}")
            else:
                print(f"{name:<{col1}}  {count:>{col2}}")
        print(sep)
        print(f"{'Unique across all files':<{col1}}  {unique_total:>{col2}}")
        return

    results: list[tuple[str, int | None]] = [(p.name, count_file(p)) for p in paths]
    print_table(results)

    if args.update_annotations:
        ann_path = Path(args.update_annotations)
        if not ann_path.exists():
            print(f"ERROR: Annotations file not found: {ann_path}", file=sys.stderr)
            sys.exit(1)
        # Build stem → count mapping (only successful counts)
        counts = {
            p.stem: count
            for p, (_, count) in zip(paths, results)
            if count is not None
        }
        update_annotations(ann_path, counts, field=args.field, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
