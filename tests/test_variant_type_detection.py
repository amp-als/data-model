"""
Unit tests for VCF variant type detection from folder structure.

Tests the new variant type detection functions that extract variant type
from folder paths and enrich VCF files with appropriate annotations.
"""

import pytest
from synapse_dataset_manager import (
    extract_variant_type_from_path,
    map_variant_type_to_enum,
    map_variant_type_to_datatype,
    generate_variant_type_keywords,
    enrich_metadata_with_file_info,
)


class TestExtractVariantTypeFromPath:
    """Test variant type extraction from folder paths."""

    def test_structural_variant_folder(self):
        """Detect structural variant from folder path."""
        path = "wgs/vcf/structural/SUBJECT001"
        assert extract_variant_type_from_path(path) == 'structural'

    def test_small_variant_folder(self):
        """Detect small variant from folder path."""
        path = "wgs/vcf/small/SUBJECT001"
        assert extract_variant_type_from_path(path) == 'small'

    def test_genomic_variant_folder(self):
        """Detect genomic variant from folder path."""
        path = "wgs/vcf/genomic/SUBJECT001"
        assert extract_variant_type_from_path(path) == 'genomic'

    def test_repeat_expansion_folder_hyphenated(self):
        """Detect repeat expansion from folder path (hyphenated)."""
        path = "wgs/vcf/repeat-expansion/SUBJECT001"
        assert extract_variant_type_from_path(path) == 'repeat_expansion'

    def test_repeat_expansion_folder_underscore(self):
        """Detect repeat expansion from folder path (underscore)."""
        path = "wgs/vcf/repeat_expansion/SUBJECT001"
        assert extract_variant_type_from_path(path) == 'repeat_expansion'

    def test_case_insensitive_structural(self):
        """Handle case-insensitive folder names."""
        assert extract_variant_type_from_path("wgs/VCF/STRUCTURAL/SUBJECT001") == 'structural'
        assert extract_variant_type_from_path("wgs/vcf/Structural/SUBJECT001") == 'structural'

    def test_case_insensitive_small(self):
        """Handle case-insensitive folder names."""
        assert extract_variant_type_from_path("wgs/VCF/SMALL/SUBJECT001") == 'small'
        assert extract_variant_type_from_path("wgs/vcf/Small/SUBJECT001") == 'small'

    def test_case_insensitive_genomic(self):
        """Handle case-insensitive folder names."""
        assert extract_variant_type_from_path("wgs/VCF/GENOMIC/SUBJECT001") == 'genomic'
        assert extract_variant_type_from_path("wgs/vcf/Genomic/SUBJECT001") == 'genomic'

    def test_empty_path(self):
        """Handle empty path."""
        assert extract_variant_type_from_path("") is None
        assert extract_variant_type_from_path(None) is None

    def test_no_variant_folder(self):
        """Return None for paths without variant folder."""
        path = "wgs/bam/SUBJECT001"
        assert extract_variant_type_from_path(path) is None

    def test_priority_order_repeat_over_structural(self):
        """Repeat-expansion takes priority in ambiguous paths."""
        # Unlikely scenario but tests priority logic
        path = "wgs/structural/repeat-expansion/SUBJECT001"
        assert extract_variant_type_from_path(path) == 'repeat_expansion'

    def test_priority_order_structural_over_small(self):
        """Structural takes priority over small in ambiguous paths."""
        path = "wgs/small/structural/SUBJECT001"
        assert extract_variant_type_from_path(path) == 'structural'

    def test_priority_order_small_over_genomic(self):
        """Small takes priority over genomic in ambiguous paths."""
        path = "wgs/genomic/small/SUBJECT001"
        assert extract_variant_type_from_path(path) == 'small'


class TestMapVariantTypeToEnum:
    """Test mapping internal variant type to VariantTypeEnum."""

    def test_structural_to_enum(self):
        """Map structural to Structural_Variant enum."""
        assert map_variant_type_to_enum('structural') == 'Structural_Variant'

    def test_small_to_enum(self):
        """Map small to Small_Variant enum."""
        assert map_variant_type_to_enum('small') == 'Small_Variant'

    def test_genomic_to_enum(self):
        """Map genomic to Genomic enum."""
        assert map_variant_type_to_enum('genomic') == 'Genomic'

    def test_repeat_expansion_to_enum(self):
        """Map repeat_expansion to Repeat_Expansion enum."""
        assert map_variant_type_to_enum('repeat_expansion') == 'Repeat_Expansion'

    def test_none_input(self):
        """Handle None input."""
        assert map_variant_type_to_enum(None) is None

    def test_empty_string(self):
        """Handle empty string."""
        assert map_variant_type_to_enum('') is None

    def test_unknown_type(self):
        """Return None for unknown variant type."""
        assert map_variant_type_to_enum('unknown_type') is None


class TestMapVariantTypeToDatatype:
    """Test mapping variant type to OmicDataTypeEnum."""

    def test_structural_to_datatype(self):
        """Map structural to StructuralVariants."""
        assert map_variant_type_to_datatype('structural') == 'StructuralVariants'

    def test_small_to_datatype(self):
        """Map small to GermlineVariants."""
        assert map_variant_type_to_datatype('small') == 'GermlineVariants'

    def test_genomic_to_datatype(self):
        """Map genomic to genomicVariants."""
        assert map_variant_type_to_datatype('genomic') == 'genomicVariants'

    def test_repeat_expansion_to_datatype(self):
        """Map repeat_expansion to genomicVariants."""
        assert map_variant_type_to_datatype('repeat_expansion') == 'genomicVariants'

    def test_none_input(self):
        """Handle None input."""
        assert map_variant_type_to_datatype(None) is None

    def test_empty_string(self):
        """Handle empty string."""
        assert map_variant_type_to_datatype('') is None


class TestGenerateVariantTypeKeywords:
    """Test keyword generation from variant type."""

    def test_structural_keywords(self):
        """Generate keywords for structural variants."""
        keywords = generate_variant_type_keywords('structural')
        assert 'structural_variants' in keywords
        assert 'cnv' in keywords
        assert 'copy_number' in keywords
        assert 'deletions' in keywords
        assert 'duplications' in keywords
        assert 'genomics' in keywords
        assert 'vcf' in keywords

    def test_small_keywords(self):
        """Generate keywords for small variants."""
        keywords = generate_variant_type_keywords('small')
        assert 'small_variants' in keywords
        assert 'snv' in keywords
        assert 'indel' in keywords
        assert 'germline' in keywords
        assert 'genomics' in keywords
        assert 'vcf' in keywords

    def test_genomic_keywords(self):
        """Generate keywords for genomic variants."""
        keywords = generate_variant_type_keywords('genomic')
        assert 'genomic_variants' in keywords
        assert 'haplotype' in keywords
        assert 'variant_calls' in keywords
        assert 'genomics' in keywords
        assert 'vcf' in keywords

    def test_repeat_expansion_keywords(self):
        """Generate keywords for repeat expansions."""
        keywords = generate_variant_type_keywords('repeat_expansion')
        assert 'repeat_expansion' in keywords
        assert 'c9orf72' in keywords
        assert 'atxn2' in keywords
        assert 'repeat_analysis' in keywords
        assert 'genomics' in keywords
        assert 'vcf' in keywords

    def test_none_input(self):
        """Handle None input."""
        assert generate_variant_type_keywords(None) == []

    def test_empty_string(self):
        """Handle empty string."""
        assert generate_variant_type_keywords('') == []

    def test_unknown_type(self):
        """Return empty list for unknown variant type."""
        assert generate_variant_type_keywords('unknown_type') == []


class TestEnrichMetadataWithFileInfoIntegration:
    """Test integration of variant type detection in enrich_metadata_with_file_info."""

    def test_vcf_structural_variant(self):
        """Enrich VCF file with structural variant type."""
        metadata = {}
        filename = "SUBJECT001.structural.vcf.gz"
        folder_path = "wgs/vcf/structural/SUBJECT001"

        result = enrich_metadata_with_file_info(metadata, filename, folder_path)

        assert result['_file_extension'] == 'vcf'
        assert result['_computed_fileFormat'] == 'VCF'
        assert result['_variant_type_detected'] == 'structural'
        assert result['_computed_variantType'] == 'Structural_Variant'
        assert result['_computed_dataType'] == 'StructuralVariants'
        assert 'structural_variants' in result['_computed_keywords']
        assert 'cnv' in result['_computed_keywords']

    def test_vcf_small_variant(self):
        """Enrich VCF file with small variant type."""
        metadata = {}
        filename = "SUBJECT001.small.vcf.gz"
        folder_path = "wgs/vcf/small/SUBJECT001"

        result = enrich_metadata_with_file_info(metadata, filename, folder_path)

        assert result['_file_extension'] == 'vcf'
        assert result['_computed_fileFormat'] == 'VCF'
        assert result['_variant_type_detected'] == 'small'
        assert result['_computed_variantType'] == 'Small_Variant'
        assert result['_computed_dataType'] == 'GermlineVariants'
        assert 'small_variants' in result['_computed_keywords']
        assert 'snv' in result['_computed_keywords']

    def test_vcf_genomic_variant(self):
        """Enrich VCF file with genomic variant type."""
        metadata = {}
        filename = "SUBJECT001.genomic.vcf.gz"
        folder_path = "wgs/vcf/genomic/SUBJECT001"

        result = enrich_metadata_with_file_info(metadata, filename, folder_path)

        assert result['_file_extension'] == 'vcf'
        assert result['_computed_fileFormat'] == 'VCF'
        assert result['_variant_type_detected'] == 'genomic'
        assert result['_computed_variantType'] == 'Genomic'
        assert result['_computed_dataType'] == 'genomicVariants'
        assert 'genomic_variants' in result['_computed_keywords']
        assert 'haplotype' in result['_computed_keywords']

    def test_vcf_repeat_expansion(self):
        """Enrich VCF file with repeat expansion type."""
        metadata = {}
        filename = "SUBJECT001.repeat.vcf.gz"
        folder_path = "wgs/vcf/repeat-expansion/SUBJECT001"

        result = enrich_metadata_with_file_info(metadata, filename, folder_path)

        assert result['_file_extension'] == 'vcf'
        assert result['_computed_fileFormat'] == 'VCF'
        assert result['_variant_type_detected'] == 'repeat_expansion'
        assert result['_computed_variantType'] == 'Repeat_Expansion'
        assert result['_computed_dataType'] == 'genomicVariants'
        assert 'repeat_expansion' in result['_computed_keywords']
        assert 'c9orf72' in result['_computed_keywords']

    def test_vcf_without_folder_path(self):
        """VCF file without folder_path gets generic annotations."""
        metadata = {}
        filename = "SUBJECT001.vcf.gz"
        folder_path = None

        result = enrich_metadata_with_file_info(metadata, filename, folder_path)

        assert result['_file_extension'] == 'vcf'
        assert result['_computed_fileFormat'] == 'VCF'
        # No variant-specific fields
        assert '_variant_type_detected' not in result
        assert '_computed_variantType' not in result
        # Generic dataType from extension mapping
        assert result['_computed_dataType'] == 'genomicVariants'

    def test_vcf_in_non_variant_folder(self):
        """VCF file in folder without variant type indicator."""
        metadata = {}
        filename = "SUBJECT001.vcf.gz"
        folder_path = "wgs/bam/SUBJECT001"

        result = enrich_metadata_with_file_info(metadata, filename, folder_path)

        assert result['_file_extension'] == 'vcf'
        assert result['_computed_fileFormat'] == 'VCF'
        # No variant-specific fields
        assert '_variant_type_detected' not in result
        assert '_computed_variantType' not in result

    def test_vcf_index_file_not_enriched(self):
        """VCF index files should not get variant type annotations."""
        metadata = {}
        filename = "SUBJECT001.vcf.gz.tbi"
        folder_path = "wgs/vcf/structural/SUBJECT001"

        result = enrich_metadata_with_file_info(metadata, filename, folder_path)

        # Extension is 'tbi', not 'vcf'
        assert result['_file_extension'] == 'tbi'
        assert result['_computed_fileFormat'] == 'TBI'
        # No variant-specific fields
        assert '_variant_type_detected' not in result
        assert '_computed_variantType' not in result

    def test_non_vcf_file_in_variant_folder(self):
        """Non-VCF files in variant folders should not get variant type."""
        metadata = {}
        filename = "SUBJECT001.bam"
        folder_path = "wgs/vcf/structural/SUBJECT001"

        result = enrich_metadata_with_file_info(metadata, filename, folder_path)

        assert result['_file_extension'] == 'bam'
        assert result['_computed_fileFormat'] == 'BAM'
        # No variant-specific fields
        assert '_variant_type_detected' not in result
        assert '_computed_variantType' not in result

    def test_backward_compatibility_no_folder_path_param(self):
        """Function still works without folder_path parameter."""
        metadata = {}
        filename = "SUBJECT001.vcf.gz"

        # Call with only two parameters (backward compatible)
        result = enrich_metadata_with_file_info(metadata, filename)

        assert result['_file_extension'] == 'vcf'
        assert result['_computed_fileFormat'] == 'VCF'
        # No variant-specific fields without folder_path
        assert '_variant_type_detected' not in result
        assert '_computed_variantType' not in result

    def test_parameter_priority_explicit_folder_path(self):
        """Explicit folder_path parameter takes priority over metadata."""
        # Simulate polluted metadata with wrong path
        metadata = {'gs_uri': 'gs://bucket/wrong/path/file.vcf.gz'}
        filename = "SUBJECT001.vcf.gz"
        folder_path = "wgs/vcf/structural/SUBJECT001"

        result = enrich_metadata_with_file_info(metadata, filename, folder_path)

        # Should use explicit folder_path, not metadata path
        assert result['_variant_type_detected'] == 'structural'
        assert result['_computed_variantType'] == 'Structural_Variant'

    def test_vcf_with_metadata_and_variant_detection(self):
        """VCF enrichment combines metadata and variant detection."""
        metadata = {'subject_id': 'SUBJECT001', 'sample_type': 'DNA'}
        filename = "SUBJECT001.structural.vcf.gz"
        folder_path = "wgs/vcf/structural/SUBJECT001"

        result = enrich_metadata_with_file_info(metadata, filename, folder_path)

        # Original metadata preserved
        assert result['subject_id'] == 'SUBJECT001'
        assert result['sample_type'] == 'DNA'
        # Variant detection fields added
        assert result['_computed_variantType'] == 'Structural_Variant'
        assert result['_computed_dataType'] == 'StructuralVariants'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
