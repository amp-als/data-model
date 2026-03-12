#!/usr/bin/env python3
"""
Verify that the fileFormat bug fix works correctly.

This script simulates the bug scenario where metadata has a polluted gs_uri
pointing to a TBI file, but we're processing a PDF file.
"""

import json
from synapse_dataset_manager import enrich_metadata_with_file_info


def test_pdf_with_polluted_metadata():
    """Test PDF file with metadata containing wrong gs_uri."""
    print("=" * 70)
    print("TEST: PDF file with polluted metadata gs_uri")
    print("=" * 70)

    # Simulate metadata with polluted gs_uri from another file
    metadata_with_wrong_uri = {
        'gs_uri': 'gs://bucket/some_other_file.txt.gz.tbi',  # Points to TBI file
        'subject_id': 'NEUBJ004MUV',
        'sample_id': 'CGND-HDA-05858'
    }

    # Process a PDF file - should use filename parameter, not metadata gs_uri
    actual_filename = 'NEUBJ004MUV.CGND-HDA-05858.L1-GZRT253.GcBiasMetrics.gc_bias.pdf'

    print(f"\nMetadata gs_uri: {metadata_with_wrong_uri['gs_uri']}")
    print(f"Actual filename: {actual_filename}")
    print()

    result = enrich_metadata_with_file_info(metadata_with_wrong_uri, actual_filename)

    print("Results:")
    print(f"  _file_extension: {result.get('_file_extension', 'N/A')}")
    print(f"  _computed_fileFormat: {result.get('_computed_fileFormat', 'N/A')}")
    print(f"  _file_category: {result.get('_file_category', 'N/A')}")
    print()

    # Verify the fix
    success = True
    if result.get('_file_extension') != 'pdf':
        print("❌ FAILED: Extension should be 'pdf', got:", result.get('_file_extension'))
        success = False
    else:
        print("✅ PASS: Extracted correct extension 'pdf'")

    if result.get('_computed_fileFormat') != 'PDF':
        print("❌ FAILED: fileFormat should be 'PDF', got:", result.get('_computed_fileFormat'))
        success = False
    else:
        print("✅ PASS: fileFormat is correctly 'PDF' (not 'TBI')")

    if result.get('_file_category') != 'gc_bias_plot':
        print("❌ FAILED: Category should be 'gc_bias_plot', got:", result.get('_file_category'))
        success = False
    else:
        print("✅ PASS: Correctly categorized as 'gc_bias_plot'")

    return success


def test_txt_with_polluted_metadata():
    """Test TXT file with metadata containing wrong gs_uri."""
    print("\n" + "=" * 70)
    print("TEST: TXT file with polluted metadata gs_uri")
    print("=" * 70)

    # Simulate metadata pointing to a different file type
    metadata_with_wrong_uri = {
        'gs_uri': 'gs://bucket/some_other_file.bam.bai',  # Points to BAI file
        'subject_id': 'SUBJECT001'
    }

    # Process a TXT.GZ file
    actual_filename = 'SUBJECT001.haplotype_calls.txt.gz'

    print(f"\nMetadata gs_uri: {metadata_with_wrong_uri['gs_uri']}")
    print(f"Actual filename: {actual_filename}")
    print()

    result = enrich_metadata_with_file_info(metadata_with_wrong_uri, actual_filename)

    print("Results:")
    print(f"  _file_extension: {result.get('_file_extension', 'N/A')}")
    print(f"  _computed_fileFormat: {result.get('_computed_fileFormat', 'N/A')}")
    print(f"  _file_category: {result.get('_file_category', 'N/A')}")
    print()

    # Verify the fix
    success = True
    if result.get('_file_extension') != 'txt':
        print("❌ FAILED: Extension should be 'txt', got:", result.get('_file_extension'))
        success = False
    else:
        print("✅ PASS: Extracted correct extension 'txt'")

    if result.get('_computed_fileFormat') != 'TXT':
        print("❌ FAILED: fileFormat should be 'TXT', got:", result.get('_computed_fileFormat'))
        success = False
    else:
        print("✅ PASS: fileFormat is correctly 'TXT' (not 'BAI')")

    if result.get('_file_category') != 'haplotype_calls':
        print("❌ FAILED: Category should be 'haplotype_calls', got:", result.get('_file_category'))
        success = False
    else:
        print("✅ PASS: Correctly categorized as 'haplotype_calls'")

    return success


def test_backward_compatibility():
    """Test that old behavior still works when no filename is provided."""
    print("\n" + "=" * 70)
    print("TEST: Backward compatibility (gs_uri fallback when no filename)")
    print("=" * 70)

    # When no filename is provided, should fall back to gs_uri
    metadata_with_gs_uri = {
        'gs_uri': 'gs://bucket/subject_123_quality_by_cycle.pdf',
        'subject_id': 'SUBJECT123'
    }

    print(f"\nMetadata gs_uri: {metadata_with_gs_uri['gs_uri']}")
    print("Filename parameter: None (not provided)")
    print()

    # Call without filename parameter
    result = enrich_metadata_with_file_info(metadata_with_gs_uri)

    print("Results:")
    print(f"  _file_extension: {result.get('_file_extension', 'N/A')}")
    print(f"  _computed_fileFormat: {result.get('_computed_fileFormat', 'N/A')}")
    print(f"  _file_category: {result.get('_file_category', 'N/A')}")
    print()

    # Verify fallback works
    success = True
    if result.get('_file_extension') != 'pdf':
        print("❌ FAILED: Should fall back to gs_uri and extract 'pdf'")
        success = False
    else:
        print("✅ PASS: Correctly fell back to gs_uri")

    if result.get('_computed_fileFormat') != 'PDF':
        print("❌ FAILED: fileFormat should be 'PDF'")
        success = False
    else:
        print("✅ PASS: fileFormat is correctly 'PDF'")

    return success


def main():
    """Run all verification tests."""
    print("\n" + "=" * 70)
    print("VERIFYING FILEFORMAT BUG FIX")
    print("=" * 70)
    print()
    print("This test verifies that the fix for the fileFormat bug works correctly.")
    print("The bug caused PDF and TXT files to get wrong fileFormat values when")
    print("metadata contained polluted gs_uri values from other files.")
    print()

    results = []

    # Run tests
    results.append(("PDF with polluted metadata", test_pdf_with_polluted_metadata()))
    results.append(("TXT with polluted metadata", test_txt_with_polluted_metadata()))
    results.append(("Backward compatibility", test_backward_compatibility()))

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    all_passed = all(result for _, result in results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print()
    if all_passed:
        print("🎉 All tests passed! The fileFormat bug is fixed.")
        return 0
    else:
        print("❌ Some tests failed. Please review the output above.")
        return 1


if __name__ == '__main__':
    exit(main())
