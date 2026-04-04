#!/usr/bin/env python3

import argparse
import subprocess
import sys
from collections import Counter


def classify(ref: str, alt: str) -> str:
    alt = alt.strip()
    ref = ref.strip()

    if alt == "" or alt == ".":
        return "MISSING_ALT"

    # Spanning deletion allele in multiallelic contexts
    if alt == "*":
        return "STAR"

    # Symbolic ALT, e.g. <DEL>, <INS>, <DUP>
    if alt.startswith("<") and alt.endswith(">"):
        return alt[1:-1]

    # Breakend notation
    if "[" in alt or "]" in alt:
        return "BND"

    # Sequence-resolved variants
    if len(ref) == 1 and len(alt) == 1:
        return "SNP"
    if len(ref) == len(alt):
        return "MNV"
    if len(ref) < len(alt):
        return "INS"
    if len(ref) > len(alt):
        return "DEL"

    return "OTHER"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Infer variant classes from REF/ALT in a bgzip-compressed VCF using bcftools query."
    )
    parser.add_argument("vcf", help="Input VCF/VCF.BGZ/VCF.GZ")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional number of records to scan (0 = scan whole file)",
    )
    args = parser.parse_args()

    cmd = ["bcftools", "query", "-f", "%REF\t%ALT\n", args.vcf]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        print("Error: bcftools not found in PATH.", file=sys.stderr)
        return 1

    allele_counts = Counter()
    site_counts = Counter()
    n_records = 0

    assert proc.stdout is not None
    for line in proc.stdout:
        if args.limit and n_records >= args.limit:
            proc.terminate()
            break

        line = line.rstrip("\n")
        if not line:
            continue

        try:
            ref, alt_field = line.split("\t", 1)
        except ValueError:
            continue

        alts = [a.strip() for a in alt_field.split(",") if a.strip()]
        if not alts:
            continue

        classes_this_site = set()

        for alt in alts:
            klass = classify(ref, alt)
            allele_counts[klass] += 1
            classes_this_site.add(klass)

        if len(classes_this_site) == 1:
            site_counts[next(iter(classes_this_site))] += 1
        else:
            site_counts["MIXED"] += 1

        n_records += 1

    stderr = proc.stderr.read() if proc.stderr is not None else ""
    return_code = proc.wait()

    # bcftools may emit header warnings; only fail hard on actual command failure
    if return_code not in (0, -15):
        print(stderr, file=sys.stderr)
        return return_code

    print(f"Records scanned\t{n_records}")
    print()

    print("ALLELE_COUNTS")
    for klass, count in sorted(allele_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"{klass}\t{count}")

    print()
    print(f"UNIQUE_ALLELE_CLASSES\t{len(allele_counts)}")
    print(f"ALLELE_CLASSES\t{','.join(sorted(allele_counts))}")

    print()
    print("SITE_COUNTS")
    for klass, count in sorted(site_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"{klass}\t{count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
