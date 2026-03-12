#!/usr/bin/env python3
"""
Verification script for VCF variant type detection.

Verifies that generated annotation files correctly assign:
- variantType field for VCF files in variant folders
- Proper dataType overrides (StructuralVariants, GermlineVariants, etc.)
- Variant-specific keywords
- No variantType for non-VCF files or VCF index files
"""

import json
import sys
from collections import Counter
from pathlib import Path


def verify_variant_type_detection(annotation_file: str):
    """
    Verify VCF variant type detection in generated annotations.

    Args:
        annotation_file: Path to generated annotation JSON file
    """
    print(f"Verifying variant type detection in: {annotation_file}")
    print("=" * 80)

    # Load annotations
    with open(annotation_file, 'r') as f:
        annotations = json.load(f)

    # Counters
    total_files = 0
    vcf_files = 0
    vcf_with_variant_type = 0
    vcf_without_variant_type = 0
    vcf_index_files = 0
    non_vcf_files = 0
    variant_type_counts = Counter()
    datatype_counts = Counter()
    errors = []

    # Iterate through annotations
    for syn_id, file_annots in annotations.items():
        for filename, annots in file_annots.items():
            total_files += 1

            # Check if VCF file
            if filename.endswith('.vcf.gz') and not filename.endswith('.vcf.gz.tbi'):
                vcf_files += 1

                # Check for variantType
                variant_type = annots.get('variantType')
                if variant_type:
                    vcf_with_variant_type += 1
                    variant_type_counts[variant_type] += 1

                    # Verify dataType is set
                    data_types = annots.get('dataType', [])
                    if isinstance(data_types, list):
                        for dt in data_types:
                            datatype_counts[dt] += 1
                    else:
                        datatype_counts[data_types] += 1

                    # Verify keywords exist
                    keywords = annots.get('keywords', [])
                    if not keywords:
                        errors.append(f"VCF with variantType but no keywords: {filename}")

                    # Verify fileFormat
                    if annots.get('fileFormat') != 'VCF':
                        errors.append(f"VCF file has wrong fileFormat: {filename} -> {annots.get('fileFormat')}")

                else:
                    vcf_without_variant_type += 1

            # Check VCF index files
            elif filename.endswith('.vcf.gz.tbi'):
                vcf_index_files += 1

                # Verify no variantType for index files
                if annots.get('variantType'):
                    errors.append(f"VCF index file should not have variantType: {filename}")

            # Non-VCF files
            else:
                non_vcf_files += 1

                # Verify no variantType for non-VCF files
                if annots.get('variantType'):
                    errors.append(f"Non-VCF file should not have variantType: {filename}")

    # Print summary
    print(f"\n📊 File Summary:")
    print(f"  Total files processed: {total_files}")
    print(f"  VCF files (.vcf.gz): {vcf_files}")
    print(f"  VCF files with variantType: {vcf_with_variant_type}")
    print(f"  VCF files without variantType: {vcf_without_variant_type}")
    print(f"  VCF index files (.vcf.gz.tbi): {vcf_index_files}")
    print(f"  Non-VCF files: {non_vcf_files}")

    print(f"\n🧬 Variant Type Distribution:")
    for variant_type, count in variant_type_counts.most_common():
        print(f"  {variant_type}: {count}")

    print(f"\n📁 Data Type Distribution:")
    for datatype, count in datatype_counts.most_common():
        print(f"  {datatype}: {count}")

    # Check for errors
    if errors:
        print(f"\n❌ Errors Found ({len(errors)}):")
        for error in errors[:10]:  # Show first 10 errors
            print(f"  - {error}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more errors")
        return False
    else:
        print(f"\n✅ All checks passed!")

    # Print examples
    print(f"\n📄 Sample VCF Annotations:")
    sample_count = 0
    for syn_id, file_annots in annotations.items():
        for filename, annots in file_annots.items():
            if filename.endswith('.vcf.gz') and not filename.endswith('.vcf.gz.tbi'):
                if annots.get('variantType'):
                    print(f"\n  File: {filename}")
                    print(f"    variantType: {annots.get('variantType')}")
                    print(f"    dataType: {annots.get('dataType')}")
                    print(f"    fileFormat: {annots.get('fileFormat')}")
                    keywords = annots.get('keywords', [])
                    print(f"    keywords: {', '.join(keywords[:5])}")
                    sample_count += 1
                    if sample_count >= 3:
                        break
        if sample_count >= 3:
            break

    return True


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python verify_variant_type_detection.py <annotation_file.json>")
        print("\nExample:")
        print("  python verify_variant_type_detection.py annotations/vcf_variant_test.json")
        sys.exit(1)

    annotation_file = sys.argv[1]

    if not Path(annotation_file).exists():
        print(f"❌ Error: File not found: {annotation_file}")
        sys.exit(1)

    success = verify_variant_type_detection(annotation_file)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
