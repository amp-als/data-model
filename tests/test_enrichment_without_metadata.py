#!/usr/bin/env python3
"""
Test that file extension mapping works even without metadata files.
"""

import sys
sys.path.insert(0, '/home/ramayyala/github/data-model')

from synapse_dataset_manager import (
    enrich_metadata_with_file_info,
    fill_template_from_metadata,
    load_mapping_dict
)


def test_enrichment_scenarios():
    """Test enrichment in different scenarios."""
    print("="*70)
    print("Testing Enrichment Scenarios")
    print("="*70)
    print()

    # Load the actual mapping file
    mapping = load_mapping_dict('mapping/target_als_test.json')

    # Create a simple template
    template = {
        'dataType': [''],
        'fileFormat': '',
        'originalSubjectId': '',
    }

    # Scenario 1: With metadata
    print("Scenario 1: With subject metadata")
    metadata = {
        'subject_id': 'TEST001',
        'age': '45',
        'sex': 'Male'
    }
    enriched = enrich_metadata_with_file_info(metadata, 'sample.bam')
    result = fill_template_from_metadata(template.copy(), enriched, mapping)

    print(f"  Filename: sample.bam")
    print(f"  dataType: {result.get('dataType', 'N/A')}")
    print(f"  fileFormat: {result.get('fileFormat', 'N/A')}")
    assert result['dataType'] == ['aligned_reads'], f"Expected ['aligned_reads'], got {result['dataType']}"
    assert result['fileFormat'] == 'BAM', f"Expected 'BAM', got {result['fileFormat']}"
    print("  ✓ Pass")
    print()

    # Scenario 2: Without metadata (empty dict)
    print("Scenario 2: Without subject metadata (empty dict)")
    metadata = {}
    enriched = enrich_metadata_with_file_info(metadata, 'variant.vcf.gz')
    result = fill_template_from_metadata(template.copy(), enriched, mapping)

    print(f"  Filename: variant.vcf.gz")
    print(f"  dataType: {result.get('dataType', 'N/A')}")
    print(f"  fileFormat: {result.get('fileFormat', 'N/A')}")
    assert result['dataType'] == ['genomicVariants'], f"Expected ['genomicVariants'], got {result['dataType']}"
    assert result['fileFormat'] == 'VCF', f"Expected 'VCF', got {result['fileFormat']}"
    print("  ✓ Pass")
    print()

    # Scenario 3: CRAM file
    print("Scenario 3: CRAM alignment file")
    metadata = {}
    enriched = enrich_metadata_with_file_info(metadata, 'NEUAJ018HDE.final.cram')
    result = fill_template_from_metadata(template.copy(), enriched, mapping)

    print(f"  Filename: NEUAJ018HDE.final.cram")
    print(f"  dataType: {result.get('dataType', 'N/A')}")
    print(f"  fileFormat: {result.get('fileFormat', 'N/A')}")
    assert result['dataType'] == ['aligned_reads'], f"Expected ['aligned_reads'], got {result['dataType']}"
    assert result['fileFormat'] == 'CRAM', f"Expected 'CRAM', got {result['fileFormat']}"
    print("  ✓ Pass")
    print()

    # Scenario 4: Index file
    print("Scenario 4: CRAI index file")
    metadata = {}
    enriched = enrich_metadata_with_file_info(metadata, 'sample.cram.crai')
    result = fill_template_from_metadata(template.copy(), enriched, mapping)

    print(f"  Filename: sample.cram.crai")
    print(f"  dataType: {result.get('dataType', 'N/A')}")
    print(f"  fileFormat: {result.get('fileFormat', 'N/A')}")
    # Index files should have empty dataType but populated fileFormat
    assert result['dataType'] == [''], f"Expected [''], got {result['dataType']}"
    assert result['fileFormat'] == 'CRAI', f"Expected 'CRAI', got {result['fileFormat']}"
    print("  ✓ Pass")
    print()

    print("="*70)
    print("✅ All scenarios passed!")
    print("="*70)
    print()
    print("Conclusion: File extension mapping works with or without metadata files!")
    print()


if __name__ == '__main__':
    test_enrichment_scenarios()
