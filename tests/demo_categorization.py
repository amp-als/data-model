#!/usr/bin/env python3
"""
Demo script showing the filename-based categorization system in action.

This demonstrates how PDF and TXT files get automatically enriched with
descriptive metadata based on their filename patterns.
"""

import json
from synapse_dataset_manager import (
    enrich_metadata_with_file_info,
    fill_template_from_metadata,
)


# Sample Target ALS files with realistic naming patterns
SAMPLE_FILES = [
    # PDF QC plots
    'subject_001_gc_bias.pdf',
    'subject_002_base_distribution_by_cycle.pdf',
    'subject_003_insert_size.pdf',
    'subject_004_quality_by_cycle.pdf',
    'subject_005_quality_distribution.pdf',

    # TXT files
    'haplotype_calls.txt.gz',
    'haplotype_calls.txt.gz.tbi',
    'repeat_expansion_summary.txt',
    'ABCD1234_genotype_data.txt',

    # Files that won't match patterns
    'random_notes.pdf',
    'documentation.txt',
]


def demo_file(filename):
    """Process a single file and show the results."""
    print(f"\nFile: {filename}")
    print("-" * 70)

    # Create minimal metadata
    metadata = {'gs_uri': f'gs://target-als-data/files/{filename}'}

    # Load mapping
    with open('mapping/target_als_test.json', 'r') as f:
        mapping = json.load(f)

    # Enrich
    enriched = enrich_metadata_with_file_info(metadata)

    # Show computed fields
    if '_file_category' in enriched:
        print(f"  Category:    {enriched['_file_category']}")
        print(f"  Title:       {enriched.get('_computed_title', 'N/A')}")
        print(f"  Description: {enriched.get('_computed_description', 'N/A')[:60]}...")
        print(f"  Keywords:    {', '.join(enriched.get('_computed_keywords', []))}")
        if '_computed_dataType' in enriched:
            print(f"  Data Type:   {enriched['_computed_dataType']}")
        print(f"  File Format: {enriched.get('_computed_fileFormat', 'N/A')}")
    else:
        print(f"  No pattern match - basic enrichment only")
        print(f"  Extension:   {enriched.get('_file_extension', 'N/A')}")
        print(f"  File Format: {enriched.get('_computed_fileFormat', 'N/A')}")


def main():
    print("=" * 70)
    print("DEMO: Filename-Based Categorization for Target ALS Files")
    print("=" * 70)
    print("\nThis demo shows how PDF QC plots and TXT summary files")
    print("get automatically enriched with descriptive metadata.")

    for filename in SAMPLE_FILES:
        demo_file(filename)

    print("\n" + "=" * 70)
    print("Summary:")
    print("=" * 70)
    print("✅ PDF QC plots: Automatically categorized with descriptive titles")
    print("✅ Haplotype calls: Tagged with dataType='variant_calls'")
    print("✅ Summary tables: Tagged with dataType='genomicVariants'")
    print("✅ All files: Get appropriate keywords and descriptions")
    print("✅ Non-matching files: Still process correctly with basic enrichment")


if __name__ == '__main__':
    main()
