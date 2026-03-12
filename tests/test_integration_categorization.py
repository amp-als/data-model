#!/usr/bin/env python3
"""
Integration test for filename-based categorization system.

Tests the full workflow from file enrichment through template filling.
"""

import json
from synapse_dataset_manager import (
    enrich_metadata_with_file_info,
    fill_template_from_metadata,
)


def test_pdf_to_annotations():
    """Test PDF file goes through full enrichment and template filling."""
    # Simulate a file from metadata CSV
    metadata_row = {
        'gs_uri': 'gs://bucket/subject_123_gc_bias.pdf',
        'file_size': '1234567',
    }

    # Load the mapping
    with open('mapping/target_als_test.json', 'r') as f:
        mapping = json.load(f)

    # Step 1: Enrich with file info
    enriched = enrich_metadata_with_file_info(metadata_row)

    print("Enriched metadata:")
    for k, v in enriched.items():
        if k.startswith('_'):
            print(f"  {k}: {v}")

    # Verify enrichment
    assert enriched['_file_extension'] == 'pdf'
    assert enriched['_file_category'] == 'gc_bias_plot'
    assert enriched['_computed_title'] == 'GC Bias QC Plot - subject_123'
    assert enriched['_computed_fileFormat'] == 'PDF'
    assert 'GC content bias' in enriched['_computed_description']
    assert 'qc' in enriched['_computed_keywords']

    # Step 2: Create template and fill
    template = {
        'title': '',
        'description': '',
        'keywords': [],
        'fileFormat': '',
        'dataType': '',
    }

    result = fill_template_from_metadata(template, enriched, mapping)

    print("\nFilled template:")
    print(json.dumps(result, indent=2))

    # Verify filled template
    assert result['title'] == 'GC Bias QC Plot - subject_123'
    assert result['description'] != ''
    assert 'qc' in result['keywords']
    assert result['fileFormat'] == 'PDF'


def test_haplotype_txt_to_annotations():
    """Test haplotype TXT file with dataType override."""
    metadata_row = {
        'gs_uri': 'gs://bucket/haplotype_calls.txt.gz',
    }

    with open('mapping/target_als_test.json', 'r') as f:
        mapping = json.load(f)

    # Enrich
    enriched = enrich_metadata_with_file_info(metadata_row)

    print("\nHaplotype enriched metadata:")
    for k, v in enriched.items():
        if k.startswith('_'):
            print(f"  {k}: {v}")

    # Verify haplotype-specific enrichment
    assert enriched['_file_extension'] == 'txt'
    assert enriched['_file_category'] == 'haplotype_calls'
    assert enriched['_computed_dataType'] == 'variant_calls'  # Override from category
    assert enriched['_computed_title'] == 'Haplotype Calls'
    assert 'variant_calls' in enriched['_computed_keywords']

    # Fill template
    template = {
        'title': '',
        'description': '',
        'keywords': [],
        'fileFormat': '',
        'dataType': '',
    }

    result = fill_template_from_metadata(template, enriched, mapping)

    print("\nHaplotype filled template:")
    print(json.dumps(result, indent=2))

    assert result['title'] == 'Haplotype Calls'
    assert result['dataType'] == 'variant_calls'
    assert result['fileFormat'] == 'TXT'
    assert 'haplotype' in result['keywords']


def test_keyword_merging():
    """Test that keywords merge instead of overwrite."""
    metadata_row = {
        'gs_uri': 'gs://bucket/insert_size.pdf',
    }

    with open('mapping/target_als_test.json', 'r') as f:
        mapping = json.load(f)

    # Enrich
    enriched = enrich_metadata_with_file_info(metadata_row)

    # Template with existing keywords
    template = {
        'title': '',
        'description': '',
        'keywords': ['existing_keyword', 'another_tag'],
        'fileFormat': '',
        'dataType': '',
    }

    result = fill_template_from_metadata(template, enriched, mapping)

    print("\nKeyword merging result:")
    print(f"  Original keywords: {template['keywords']}")
    print(f"  Computed keywords: {enriched['_computed_keywords']}")
    print(f"  Merged keywords: {result['keywords']}")

    # Verify merging
    assert 'existing_keyword' in result['keywords']
    assert 'another_tag' in result['keywords']
    assert 'qc' in result['keywords']
    assert 'insert_size' in result['keywords']
    # Check deduplication
    assert len(result['keywords']) == len(set(result['keywords']))


def test_non_matching_file():
    """Test that files without pattern matches still work."""
    metadata_row = {
        'gs_uri': 'gs://bucket/random_document.pdf',
    }

    with open('mapping/target_als_test.json', 'r') as f:
        mapping = json.load(f)

    enriched = enrich_metadata_with_file_info(metadata_row)

    print("\nNon-matching file enrichment:")
    for k, v in enriched.items():
        if k.startswith('_'):
            print(f"  {k}: {v}")

    # Should have basic enrichment but no category-specific fields
    assert enriched['_file_extension'] == 'pdf'
    assert enriched['_computed_fileFormat'] == 'PDF'
    assert '_file_category' not in enriched
    assert '_computed_title' not in enriched
    assert '_computed_keywords' not in enriched

    # Template filling should work but won't add title/keywords
    template = {
        'title': '',
        'description': '',
        'keywords': [],
        'fileFormat': '',
        'dataType': '',
    }

    result = fill_template_from_metadata(template, enriched, mapping)

    print("\nNon-matching filled template:")
    print(json.dumps(result, indent=2))

    assert result['fileFormat'] == 'PDF'
    assert result['title'] == ''  # No computed title
    assert result['keywords'] == []  # No computed keywords


if __name__ == '__main__':
    print("=" * 70)
    print("INTEGRATION TEST: Filename-Based Categorization")
    print("=" * 70)

    test_pdf_to_annotations()
    print("\n" + "=" * 70)

    test_haplotype_txt_to_annotations()
    print("\n" + "=" * 70)

    test_keyword_merging()
    print("\n" + "=" * 70)

    test_non_matching_file()
    print("\n" + "=" * 70)

    print("\n✅ All integration tests passed!")
