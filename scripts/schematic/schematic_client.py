#!/usr/bin/env python3
"""
schematic_api.py — Minimal CLI for the public Schematic REST API (v1)

Commands:
  - generate-manifest  -> GET /manifest/generate (excel or csv; csv via local conversion)
  - validate-manifest  -> POST /manifest/validate (multipart)

Examples:
  # Excel
  python schematic_api.py generate-manifest \
    --data-type Clinical \
    --schema-url https://raw.githubusercontent.com/Sage-Bionetworks/schematic/main/examples/data_model/example.model.jsonld \
    --out manifest_Clinical.xlsx

  # CSV (requests excel, converts locally, deletes the temp .xlsx)
  python schematic_api.py generate-manifest \
    --data-type Clinical \
    --schema-url https://raw.githubusercontent.com/Sage-Bionetworks/schematic/main/examples/data_model/example.model.jsonld \
    --output-format csv \
    --out manifest_Clinical.csv

  # Validate
  python schematic_api.py validate-manifest \
    --data-type Clinical \
    --file manifest_Clinical.xlsx
"""

from __future__ import annotations
import argparse
import io
import json
import os
import pathlib
import sys
import tempfile
from typing import Any, Dict

import pandas as pd  # pip install pandas openpyxl
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_BASE = os.getenv("SCHEMATIC_BASE_URL", "https://schematic.api.sagebionetworks.org/v1")


# ---------- HTTP helpers ----------

def build_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Accept": "application/json", "User-Agent": "schematic-min-cli/0.4"})
    retry = Retry(
        total=4,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s

def url_join(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return base + path

def fail_with_response(r: requests.Response) -> None:
    try:
        body = r.json()
        msg = json.dumps(body, indent=2)
    except Exception:
        msg = r.text
    sys.exit(f"HTTP {r.status_code} @ {r.request.method} {r.url}\n{msg}")


# ---------- File helpers ----------

def _xlsx_bytes_to_csv(xlsx_bytes: bytes, csv_path: pathlib.Path, sheet: str | int | None = None) -> None:
    """Convert in-memory .xlsx bytes to CSV on disk (first sheet by default)."""
    with io.BytesIO(xlsx_bytes) as bio:
        df = pd.read_excel(bio, sheet_name=sheet, engine="openpyxl")
        if isinstance(df, dict):  # If multiple sheets, pick the first
            df = next(iter(df.values()))
        df.to_csv(csv_path, index=False)


# ---------- Commands ----------

def cmd_generate_manifest(args: argparse.Namespace) -> None:
    session = build_session()

    # API supports: {"excel", "google_sheet", "dataframe (only if getting existing manifests)"}
    # We support "csv" by requesting excel and converting locally.
    request_format = "excel" if args.output_format == "csv" else args.output_format

    params: Dict[str, Any] = {
        "data_type": args.data_type,
        "schema_url": args.schema_url,
        "output_format": request_format,
    }
    if args.dataset_id:
        params["dataset_id"] = args.dataset_id

    r = session.get(
        url_join(args.base_url, "/manifest/generate"),
        params=params,
        timeout=args.timeout,
        stream=True,
    )
    if not r.ok:
        fail_with_response(r)

    content = b"".join(r.iter_content(8192))
    outpath = pathlib.Path(args.out)

    if args.output_format == "csv":
        # Write to a temp .xlsx, then convert, then delete
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(content)
            tmp_path = pathlib.Path(tmp.name)

        if outpath.suffix.lower() != ".csv":
            outpath = outpath.with_suffix(".csv")

        _xlsx_bytes_to_csv(tmp_path.read_bytes(), outpath, sheet=None)
        tmp_path.unlink(missing_ok=True)  # delete temp .xlsx
        print(f"Saved CSV: {outpath}")
    else:
        if outpath.suffix.lower() != ".xlsx":
            outpath = outpath.with_suffix(".xlsx")
        with open(outpath, "wb") as f:
            f.write(content)
        print(f"Saved Excel: {outpath}")


def cmd_validate_manifest(args: argparse.Namespace) -> None:
    session = build_session()
    fpath = pathlib.Path(args.file)
    if not fpath.exists():
        sys.exit(f"File not found: {fpath}")

    files = {"file": (fpath.name, open(fpath, "rb"))}
    data = {"data_type": args.data_type}
    if args.dataset_id:
        data["dataset_id"] = args.dataset_id

    try:
        r = session.post(
            url_join(args.base_url, "/manifest/validate"),
            files=files,
            data=data,
            timeout=args.timeout,
        )
    finally:
        files["file"][1].close()

    if not r.ok:
        fail_with_response(r)

    try:
        print(json.dumps(r.json(), indent=2))
    except Exception:
        print(r.text)


# ---------- CLI plumbing ----------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Minimal Schematic REST API CLI (v1)")
    p.add_argument("--base-url", default=DEFAULT_BASE, help=f"API base URL (default: {DEFAULT_BASE})")
    p.add_argument("--timeout", type=int, default=300, help="HTTP timeout in seconds")

    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("generate-manifest", help="GET /manifest/generate (download Excel or CSV)")
    sp.add_argument("--data-type", required=True, help="Component name (e.g., Clinical, Dataset, RNAseq)")
    sp.add_argument("--schema-url", required=True, help="URL to JSON-LD model")
    sp.add_argument("--output-format", default="excel", choices=["excel", "csv"], help="Desired output")
    sp.add_argument("--dataset-id", help="Optional dataset/project ID")
    sp.add_argument("--out", default="manifest.xlsx", help="Output file path")
    sp.set_defaults(func=cmd_generate_manifest)

    sp = sub.add_parser("validate-manifest", help="POST /manifest/validate (multipart)")
    sp.add_argument("--data-type", required=True)
    sp.add_argument("--file", required=True)
    sp.add_argument("--dataset-id")
    sp.set_defaults(func=cmd_validate_manifest)

    return p

def main(argv=None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)

if __name__ == "__main__":
    main()

