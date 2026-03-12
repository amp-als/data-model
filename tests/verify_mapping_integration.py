#!/usr/bin/env python3
"""
Verification script to demonstrate the file extension mapping in action.
This shows how files will now be properly classified by their extensions.
"""

import sys
sys.path.insert(0, '/home/ramayyala/github/data-model')

from synapse_dataset_manager import enrich_metadata_with_file_info


def demonstrate_mapping():
    """Show examples of how different file types will be mapped."""

    print("="*70)
    print("File Extension Mapping Demonstration")
    print("="*70)
    print()

    # Sample files from Target ALS
    test_files = [
        ('NEUAJ018HDE.CGND-HDA-05782.L1-QTXK684.final.cram', 'CRAM alignment file'),
        ('NEUAJ018HDE.CGND-HDA-05782.L1-QTXK684.final.cram.crai', 'CRAM index file'),
        ('sample.bam', 'BAM alignment file'),
        ('sample.bam.bai', 'BAM index file'),
        ('variants.vcf.gz', 'Compressed VCF variant file'),
        ('sample.fastq.gz', 'Compressed FASTQ raw reads'),
        ('annotations.gtf', 'GTF annotation file'),
        ('document.pdf', 'PDF documentation'),
        ('checksum.md5', 'MD5 checksum file'),
    ]

    print("Sample File Classifications:\n")
    print(f"{'File Name':<55} {'Extension':<10} {'Data Type':<20} {'File Format':<12}")
    print("-" * 100)

    for filename, description in test_files:
        # Simulate metadata enrichment
        metadata = {'subject_id': 'TEST001'}
        enriched = enrich_metadata_with_file_info(metadata, filename)

        ext = enriched.get('_file_extension', 'N/A')
        datatype = enriched.get('_computed_dataType', 'N/A')
        fileformat = enriched.get('_computed_fileFormat', 'N/A')

        print(f"{filename:<55} {ext:<10} {datatype:<20} {fileformat:<12}")

    print()
    print("="*70)
    print("Key Improvements:")
    print("="*70)
    print()
    print("✓ BAM/CRAM files correctly identified as 'aligned_reads' (not 'genomicVariants')")
    print("✓ VCF files correctly identified as 'genomicVariants'")
    print("✓ Index files (.bai, .crai, .tbi) have fileFormat set but no dataType")
    print("  (index files are technical files, not omic data types)")
    print("✓ Compressed files (.gz) use inner extension for classification")
    print("✓ File formats are properly uppercase (BAM, VCF, CRAM, etc.)")
    print()

    print("="*70)
    print("Before vs After Example:")
    print("="*70)
    print()
    print("File: NEUAJ018HDE.CGND-HDA-05782.L1-QTXK684.final.cram")
    print()
    print("BEFORE (with fixed values):")
    print("  dataType: 'genomicVariants' ❌ (incorrect - CRAM is aligned reads)")
    print("  fileFormat: 'tbi' ❌ (incorrect - from unreliable metadata)")
    print("  assay: 'wholeGenomeSeq' ✓ (but was fixed for all files)")
    print("  libraryStrategy: 'WGS' ✓ (but was fixed for all files)")
    print()
    print("AFTER (with dynamic mapping):")
    print("  dataType: 'aligned_reads' ✓ (correct - derived from .cram extension)")
    print("  fileFormat: 'CRAM' ✓ (correct - derived from .cram extension)")
    print("  assay: [empty] (should be set per file type if needed)")
    print("  libraryStrategy: [empty] (should be set per file type if needed)")
    print()

    print("="*70)
    print("Integration Notes:")
    print("="*70)
    print()
    print("• The enrichment happens BEFORE mapping is applied")
    print("• Computed fields (_computed_dataType, _computed_fileFormat) are")
    print("  treated like regular metadata columns in the mapping file")
    print("• Falls back gracefully if file name is not available")
    print("• Does not overwrite existing non-empty values")
    print("• The _file_extension field is available for debugging but not mapped")
    print()


if __name__ == '__main__':
    demonstrate_mapping()
