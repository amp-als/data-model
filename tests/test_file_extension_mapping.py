#!/usr/bin/env python3
"""
Test script for file extension mapping functions.
Validates that the dynamic file extension mapping works correctly.
"""

import sys
sys.path.insert(0, '/home/ramayyala/github/data-model')

from synapse_dataset_manager import (
    extract_file_extension,
    map_extension_to_datatype,
    map_extension_to_fileformat,
    enrich_metadata_with_file_info
)


def test_extract_file_extension():
    """Test the file extension extraction function."""
    print("Testing extract_file_extension()...")

    test_cases = [
        ('sample.bam', 'bam'),
        ('gs://bucket/file.cram', 'cram'),
        ('data.vcf.gz', 'vcf'),  # compressed file - use inner extension
        ('index.bam.bai', 'bai'),
        ('noext', ''),
        ('file.fastq.gz', 'fastq'),
        ('/path/to/sample.BAM', 'bam'),  # case insensitive
        ('', ''),
    ]

    passed = 0
    failed = 0

    for input_val, expected in test_cases:
        result = extract_file_extension(input_val)
        if result == expected:
            print(f"  ✓ '{input_val}' -> '{result}'")
            passed += 1
        else:
            print(f"  ✗ '{input_val}' -> '{result}' (expected '{expected}')")
            failed += 1

    print(f"\nPassed: {passed}/{len(test_cases)}\n")
    return failed == 0


def test_map_extension_to_datatype():
    """Test the extension to dataType mapping function."""
    print("Testing map_extension_to_datatype()...")

    test_cases = [
        ('bam', 'aligned_reads'),
        ('cram', 'aligned_reads'),
        ('sam', 'aligned_reads'),
        ('vcf', 'genomicVariants'),
        ('bcf', 'genomicVariants'),
        ('fastq', 'raw_sequencing'),
        ('fq', 'raw_sequencing'),
        ('bai', ''),  # index files have no dataType (not omic data)
        ('crai', ''),  # index files have no dataType (not omic data)
        ('tbi', ''),  # index files have no dataType (not omic data)
        ('gtf', 'genome_annotation'),
        ('gff', 'genome_annotation'),
        ('bed', 'genome_annotation'),
        ('unknown', ''),
        ('gz', ''),  # compression format, no data type
        ('pdf', ''),
    ]

    passed = 0
    failed = 0

    for input_val, expected in test_cases:
        result = map_extension_to_datatype(input_val)
        if result == expected:
            print(f"  ✓ '{input_val}' -> '{result}'")
            passed += 1
        else:
            print(f"  ✗ '{input_val}' -> '{result}' (expected '{expected}')")
            failed += 1

    print(f"\nPassed: {passed}/{len(test_cases)}\n")
    return failed == 0


def test_map_extension_to_fileformat():
    """Test the extension to fileFormat mapping function."""
    print("Testing map_extension_to_fileformat()...")

    test_cases = [
        ('bam', 'BAM'),
        ('vcf', 'VCF'),
        ('fastq', 'FASTQ'),
        ('fq', 'FASTQ'),
        ('cram', 'CRAM'),
        ('bai', 'BAI'),
        ('gz', 'GZIP'),
        ('pdf', 'PDF'),
        ('txt', 'TXT'),
        ('md5', 'MD5'),
    ]

    passed = 0
    failed = 0

    for input_val, expected in test_cases:
        result = map_extension_to_fileformat(input_val)
        if result == expected:
            print(f"  ✓ '{input_val}' -> '{result}'")
            passed += 1
        else:
            print(f"  ✗ '{input_val}' -> '{result}' (expected '{expected}')")
            failed += 1

    print(f"\nPassed: {passed}/{len(test_cases)}\n")
    return failed == 0


def test_enrich_metadata_with_file_info():
    """Test the metadata enrichment function."""
    print("Testing enrich_metadata_with_file_info()...")

    # Test with file_name parameter
    metadata = {'subject_id': 'S001'}
    enriched = enrich_metadata_with_file_info(metadata, 'sample.bam')

    assert enriched['_file_extension'] == 'bam', f"Expected 'bam', got '{enriched.get('_file_extension')}'"
    assert enriched['_computed_dataType'] == 'aligned_reads', f"Expected 'aligned_reads', got '{enriched.get('_computed_dataType')}'"
    assert enriched['_computed_fileFormat'] == 'BAM', f"Expected 'BAM', got '{enriched.get('_computed_fileFormat')}'"
    print("  ✓ Enrichment from file_name parameter")

    # Test with gs_uri in metadata
    metadata = {'subject_id': 'S002', 'gs_uri': 'gs://bucket/path/variant.vcf.gz'}
    enriched = enrich_metadata_with_file_info(metadata)

    assert enriched['_file_extension'] == 'vcf', f"Expected 'vcf', got '{enriched.get('_file_extension')}'"
    assert enriched['_computed_dataType'] == 'genomicVariants', f"Expected 'genomicVariants', got '{enriched.get('_computed_dataType')}'"
    assert enriched['_computed_fileFormat'] == 'VCF', f"Expected 'VCF', got '{enriched.get('_computed_fileFormat')}'"
    print("  ✓ Enrichment from gs_uri in metadata")

    # Test with no file info
    metadata = {'subject_id': 'S003'}
    enriched = enrich_metadata_with_file_info(metadata)

    assert '_file_extension' not in enriched, "Should not add extension if no file info"
    print("  ✓ No enrichment when no file info available")

    # Test with index file
    metadata = {'subject_id': 'S004'}
    enriched = enrich_metadata_with_file_info(metadata, 'sample.bam.bai')

    assert enriched['_file_extension'] == 'bai', f"Expected 'bai', got '{enriched.get('_file_extension')}'"
    assert enriched.get('_computed_dataType', '') == '', f"Expected empty dataType for index, got '{enriched.get('_computed_dataType')}'"
    assert enriched['_computed_fileFormat'] == 'BAI', f"Expected 'BAI', got '{enriched.get('_computed_fileFormat')}'"
    print("  ✓ Index file correctly identified (no dataType, has fileFormat)")

    print(f"\nAll enrichment tests passed!\n")
    return True


if __name__ == '__main__':
    print("="*60)
    print("File Extension Mapping Tests")
    print("="*60 + "\n")

    all_passed = True
    all_passed &= test_extract_file_extension()
    all_passed &= test_map_extension_to_datatype()
    all_passed &= test_map_extension_to_fileformat()
    all_passed &= test_enrich_metadata_with_file_info()

    print("="*60)
    if all_passed:
        print("✅ ALL TESTS PASSED!")
    else:
        print("❌ SOME TESTS FAILED")
    print("="*60)

    sys.exit(0 if all_passed else 1)
