#!/usr/bin/env python3
"""
Unit tests for filename-based categorization system.

Tests pattern matching, metadata generation, and enrichment integration
for Target ALS PDF and TXT files.
"""

import pytest
from synapse_dataset_manager import (
    extract_file_category,
    generate_title_from_category,
    generate_description_from_category,
    generate_keywords_from_category,
    get_datatype_from_category,
    enrich_metadata_with_file_info,
)


class TestPdfPatternMatching:
    """Test PDF QC plot pattern detection."""

    def test_gc_bias_underscore(self):
        assert extract_file_category('subject_001_gc_bias.pdf') == 'gc_bias_plot'

    def test_gc_bias_hyphen(self):
        assert extract_file_category('gc-bias-plot.pdf') == 'gc_bias_plot'

    def test_gc_bias_no_separator(self):
        assert extract_file_category('gcbias.pdf') == 'gc_bias_plot'

    def test_base_distribution(self):
        assert extract_file_category('base_distribution_by_cycle.pdf') == 'base_distribution_plot'

    def test_insert_size(self):
        assert extract_file_category('insert_size.pdf') == 'insert_size_histogram'

    def test_quality_by_cycle(self):
        assert extract_file_category('quality_by_cycle.pdf') == 'quality_by_cycle_plot'

    def test_quality_distribution(self):
        assert extract_file_category('quality_distribution.pdf') == 'quality_distribution_plot'


class TestTxtPatternMatching:
    """Test TXT file pattern detection."""

    def test_haplotype_calls_gz(self):
        assert extract_file_category('haplotype_calls.txt.gz') == 'haplotype_calls'

    def test_haplotype_calls_tbi(self):
        assert extract_file_category('haplotype_calls.txt.gz.tbi') == 'haplotype_calls'

    def test_haplotype_call_singular(self):
        assert extract_file_category('haplotype_call.txt') == 'haplotype_calls'

    def test_summary_keyword(self):
        assert extract_file_category('repeat_expansion_summary.txt') == 'summary_table'

    def test_repeat_id(self):
        assert extract_file_category('repeat_id_results.txt') == 'summary_table'

    def test_genotype(self):
        assert extract_file_category('genotype_data.txt') == 'summary_table'


class TestNoMatchGraceful:
    """Test that unmatched files are handled gracefully."""

    def test_random_pdf(self):
        assert extract_file_category('random_file.pdf') is None

    def test_random_txt(self):
        assert extract_file_category('some_data.txt') is None

    def test_empty_string(self):
        assert extract_file_category('') is None

    def test_none(self):
        assert extract_file_category(None) is None


class TestTitleGeneration:
    """Test title generation with subject ID extraction."""

    def test_gc_bias_with_subject(self):
        title = generate_title_from_category('gc_bias_plot', 'subject_001_gc_bias.pdf')
        assert 'GC Bias QC Plot' in title
        assert 'subject_001' in title

    def test_haplotype_without_subject(self):
        title = generate_title_from_category('haplotype_calls', 'haplotype_calls.txt.gz')
        assert title == 'Haplotype Calls'

    def test_subject_uppercase(self):
        title = generate_title_from_category('summary_table', 'ABCD1234_repeat_summary.txt')
        assert 'ABCD1234' in title

    def test_unknown_category(self):
        title = generate_title_from_category('unknown_category', 'file.pdf')
        assert title == 'File'


class TestDescriptionGeneration:
    """Test description generation."""

    def test_gc_bias_description(self):
        desc = generate_description_from_category('gc_bias_plot')
        assert 'GC content bias' in desc
        assert len(desc) <= 500

    def test_haplotype_description(self):
        desc = generate_description_from_category('haplotype_calls')
        assert 'haplotype' in desc.lower()
        assert 'variant' in desc.lower()
        assert len(desc) <= 500

    def test_all_descriptions_length(self):
        categories = [
            'gc_bias_plot', 'base_distribution_plot', 'insert_size_histogram',
            'quality_by_cycle_plot', 'quality_distribution_plot',
            'haplotype_calls', 'summary_table'
        ]
        for category in categories:
            desc = generate_description_from_category(category)
            assert len(desc) <= 500, f"Description for {category} exceeds 500 chars"

    def test_unknown_category_empty(self):
        desc = generate_description_from_category('unknown_category')
        assert desc == ''


class TestKeywordGeneration:
    """Test keyword generation."""

    def test_gc_bias_keywords(self):
        keywords = generate_keywords_from_category('gc_bias_plot')
        assert 'qc' in keywords
        assert 'quality_control' in keywords
        assert 'gc_bias' in keywords

    def test_haplotype_keywords(self):
        keywords = generate_keywords_from_category('haplotype_calls')
        assert 'variant_calls' in keywords
        assert 'haplotype' in keywords
        assert 'genomics' in keywords

    def test_summary_keywords(self):
        keywords = generate_keywords_from_category('summary_table')
        assert 'repeat_expansion' in keywords
        assert 'c9orf72' in keywords
        assert 'atxn2' in keywords

    def test_all_keywords_are_lists(self):
        categories = [
            'gc_bias_plot', 'base_distribution_plot', 'insert_size_histogram',
            'quality_by_cycle_plot', 'quality_distribution_plot',
            'haplotype_calls', 'summary_table'
        ]
        for category in categories:
            keywords = generate_keywords_from_category(category)
            assert isinstance(keywords, list)
            assert all(isinstance(k, str) for k in keywords)

    def test_unknown_category_empty_list(self):
        keywords = generate_keywords_from_category('unknown_category')
        assert keywords == []


class TestDataTypeMapping:
    """Test category to dataType mapping."""

    def test_haplotype_calls_datatype(self):
        assert get_datatype_from_category('haplotype_calls') == 'variant_calls'

    def test_summary_table_datatype(self):
        assert get_datatype_from_category('summary_table') == 'genomicVariants'

    def test_qc_plot_no_datatype(self):
        assert get_datatype_from_category('gc_bias_plot') is None
        assert get_datatype_from_category('quality_by_cycle_plot') is None

    def test_unknown_category_no_datatype(self):
        assert get_datatype_from_category('unknown_category') is None


class TestEnrichmentIntegration:
    """Test integration of categorization into enrichment function."""

    def test_pdf_enrichment(self):
        result = enrich_metadata_with_file_info({}, 'subject_001_gc_bias.pdf')
        assert result['_file_extension'] == 'pdf'
        assert result['_file_category'] == 'gc_bias_plot'
        assert 'GC Bias' in result['_computed_title']
        assert result['_computed_description'] != ''
        assert 'qc' in result['_computed_keywords']
        assert result['_computed_fileFormat'] == 'PDF'

    def test_txt_haplotype_enrichment(self):
        result = enrich_metadata_with_file_info({}, 'haplotype_calls.txt.gz')
        assert result['_file_extension'] == 'txt'
        assert result['_file_category'] == 'haplotype_calls'
        assert result['_computed_title'] == 'Haplotype Calls'
        assert result['_computed_dataType'] == 'variant_calls'
        assert 'variant_calls' in result['_computed_keywords']

    def test_txt_summary_enrichment(self):
        result = enrich_metadata_with_file_info({}, 'repeat_expansion_summary.txt')
        assert result['_file_extension'] == 'txt'
        assert result['_file_category'] == 'summary_table'
        assert result['_computed_dataType'] == 'genomicVariants'

    def test_tbi_index_no_datatype_override(self):
        # .tbi files should get fileFormat but not dataType override
        result = enrich_metadata_with_file_info({}, 'haplotype_calls.txt.gz.tbi')
        assert result['_file_extension'] == 'tbi'
        assert result['_computed_fileFormat'] == 'TBI'
        # TBI is not in ['pdf', 'txt'], so no category enrichment should happen
        assert '_file_category' not in result

    def test_no_match_still_processes(self):
        result = enrich_metadata_with_file_info({}, 'random_file.pdf')
        assert result['_file_extension'] == 'pdf'
        assert result['_computed_fileFormat'] == 'PDF'
        assert '_file_category' not in result
        assert '_computed_title' not in result

    def test_enrichment_with_gs_uri(self):
        result = enrich_metadata_with_file_info(
            {'gs_uri': 'gs://bucket/subject_123_quality_by_cycle.pdf'}
        )
        assert result['_file_category'] == 'quality_by_cycle_plot'
        assert 'subject_123' in result['_computed_title']

    def test_enrichment_without_file_identifier(self):
        result = enrich_metadata_with_file_info({})
        assert result == {}

    def test_non_pdf_txt_no_category_enrichment(self):
        result = enrich_metadata_with_file_info({}, 'data.bam')
        assert result['_file_extension'] == 'bam'
        assert '_file_category' not in result
        assert '_computed_title' not in result

    def test_file_name_parameter_priority(self):
        """Test that file_name parameter takes priority over metadata gs_uri."""
        # Simulate metadata with a polluted gs_uri (from another file)
        metadata_with_wrong_uri = {
            'gs_uri': 'gs://bucket/wrong_file.txt.gz.tbi',  # Points to TBI file
            'subject_id': 'NEUBJ004MUV'
        }

        # Process a PDF file - should use the filename parameter, not metadata gs_uri
        actual_filename = 'NEUBJ004MUV.gc_bias.pdf'
        result = enrich_metadata_with_file_info(metadata_with_wrong_uri, actual_filename)

        # Should extract extension from actual_filename, not from metadata gs_uri
        assert result['_file_extension'] == 'pdf', \
            "Should extract 'pdf' from filename parameter, not 'tbi' from metadata gs_uri"
        assert result['_computed_fileFormat'] == 'PDF', \
            "PDF file should get fileFormat='PDF', not 'TBI'"
        assert result.get('_file_category') == 'gc_bias_plot', \
            "PDF filename should be categorized correctly"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
