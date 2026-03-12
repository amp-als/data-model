#!/usr/bin/env python3
"""
Quick demonstration of VCF variant type detection.

Shows how the detection functions work with different folder structures.
"""

from synapse_dataset_manager import (
    extract_variant_type_from_path,
    map_variant_type_to_enum,
    map_variant_type_to_datatype,
    generate_variant_type_keywords,
    enrich_metadata_with_file_info,
)


def demo_path_detection():
    """Demonstrate folder path detection."""
    print("=" * 80)
    print("VCF Variant Type Detection - Demo")
    print("=" * 80)

    test_paths = [
        ("wgs/vcf/structural/SUBJECT001", "Structural variants folder"),
        ("wgs/vcf/small/SUBJECT001", "Small variants folder"),
        ("wgs/vcf/genomic/SUBJECT001", "Genomic variants folder"),
        ("wgs/vcf/repeat-expansion/SUBJECT001", "Repeat expansion folder"),
        ("wgs/bam/SUBJECT001", "No variant folder"),
    ]

    print("\n1. Folder Path Detection")
    print("-" * 80)

    for path, description in test_paths:
        variant_type = extract_variant_type_from_path(path)
        print(f"\nPath: {path}")
        print(f"  Description: {description}")
        print(f"  Detected type: {variant_type or 'None'}")

        if variant_type:
            enum_value = map_variant_type_to_enum(variant_type)
            datatype = map_variant_type_to_datatype(variant_type)
            keywords = generate_variant_type_keywords(variant_type)

            print(f"  VariantTypeEnum: {enum_value}")
            print(f"  DataType: {datatype}")
            print(f"  Keywords: {', '.join(keywords[:4])}...")


def demo_enrichment():
    """Demonstrate full enrichment pipeline."""
    print("\n\n2. Full Enrichment Pipeline")
    print("-" * 80)

    test_cases = [
        {
            "filename": "SUBJECT001.structural.vcf.gz",
            "folder_path": "wgs/vcf/structural/SUBJECT001",
            "description": "Structural variant VCF"
        },
        {
            "filename": "SUBJECT002.small.vcf.gz",
            "folder_path": "wgs/vcf/small/SUBJECT002",
            "description": "Small variant VCF"
        },
        {
            "filename": "SUBJECT003.genomic.vcf.gz",
            "folder_path": "wgs/vcf/genomic/SUBJECT003",
            "description": "Genomic variant VCF"
        },
        {
            "filename": "SUBJECT004.vcf.gz.tbi",
            "folder_path": "wgs/vcf/structural/SUBJECT004",
            "description": "VCF index file (should not get variantType)"
        },
        {
            "filename": "SUBJECT005.bam",
            "folder_path": "wgs/bam/SUBJECT005",
            "description": "Non-VCF file (should not get variantType)"
        },
    ]

    for test in test_cases:
        print(f"\n{test['description']}")
        print(f"  File: {test['filename']}")
        print(f"  Folder: {test['folder_path']}")

        result = enrich_metadata_with_file_info(
            {},
            test['filename'],
            test['folder_path']
        )

        print(f"\n  Enriched fields:")
        print(f"    _file_extension: {result.get('_file_extension')}")
        print(f"    _computed_fileFormat: {result.get('_computed_fileFormat')}")
        print(f"    _computed_dataType: {result.get('_computed_dataType')}")

        if '_computed_variantType' in result:
            print(f"    _computed_variantType: {result.get('_computed_variantType')}")
            print(f"    _variant_type_detected: {result.get('_variant_type_detected')}")
            keywords = result.get('_computed_keywords', [])
            print(f"    _computed_keywords: {', '.join(keywords[:4])}...")
        else:
            print(f"    _computed_variantType: (not set)")


def demo_summary():
    """Show summary of mappings."""
    print("\n\n3. Variant Type Mappings Summary")
    print("-" * 80)

    mappings = [
        ("structural", "Structural variants (DEL, INS, DUP, INV, CNVs)"),
        ("small", "Small variants (SNVs and InDels)"),
        ("genomic", "All variant types (genome-wide haplotype calls)"),
        ("repeat_expansion", "Repeat expansions (C9orf72, ATXN2, etc.)"),
    ]

    print("\n{:<20} {:<25} {:<25} {}".format(
        "Folder", "VariantTypeEnum", "OmicDataTypeEnum", "Description"
    ))
    print("-" * 80)

    for variant_type, description in mappings:
        folder = variant_type.replace('_', '-')
        enum_value = map_variant_type_to_enum(variant_type)
        datatype = map_variant_type_to_datatype(variant_type)

        print(f"{folder + '/':<20} {enum_value:<25} {datatype:<25}")
        print(f"{'':20} {description}")
        print()


if __name__ == '__main__':
    demo_path_detection()
    demo_enrichment()
    demo_summary()

    print("\n" + "=" * 80)
    print("✅ Demo completed successfully!")
    print("=" * 80)
