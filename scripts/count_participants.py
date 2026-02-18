#!/usr/bin/env python3
"""Count participants in CSV and plain-text files.

Participant count = number of data rows (total rows minus header row).

Optionally writes recordCount back to a file-annotations JSON file using
the CSV filename stem as the key matched against each entry's viewName field.
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


def count_csv(path: Path) -> int | None:
    """Count rows in a CSV file using pandas (handles quoted newlines)."""
    try:
        df = pd.read_csv(path)
        return len(df)
    except Exception as e:
        print(f"WARNING: Could not read {path}: {e}", file=sys.stderr)
        return None


def count_txt(path: Path) -> int | None:
    """Count data rows in a plain-text file (total lines minus 1 header)."""
    try:
        total = sum(1 for _ in open(path, encoding="utf-8"))
        if total == 0:
            print(f"WARNING: {path} is empty, skipping.", file=sys.stderr)
            return None
        return total - 1
    except Exception as e:
        print(f"WARNING: Could not read {path}: {e}", file=sys.stderr)
        return None


def count_file(path: Path) -> int | None:
    """Dispatch to the appropriate counter based on file extension."""
    if not path.exists():
        print(f"WARNING: File not found: {path}", file=sys.stderr)
        return None
    if path.stat().st_size == 0:
        print(f"WARNING: {path} is empty, skipping.", file=sys.stderr)
        return None
    if path.suffix.lower() == ".csv":
        return count_csv(path)
    else:
        return count_txt(path)


def collect_files(directory: Path, recursive: bool) -> list[Path]:
    """Return all .csv and .txt files in a directory."""
    pattern = "**/*" if recursive else "*"
    files = []
    for ext in (".csv", ".txt"):
        files.extend(directory.glob(pattern + ext))
    return sorted(files)


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
        description="Count participants (data rows) in CSV and TXT files."
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
        help="Directory to scan for .csv and .txt files.",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Scan --dir recursively.",
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
