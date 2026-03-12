# Filename-Based Categorization Guide

## Quick Start

The filename-based categorization system automatically enriches PDF and TXT files with descriptive metadata based on their filenames. No configuration required!

## What Gets Categorized?

### PDF Files (QC Plots)
Files matching these patterns get automatically categorized:

| Pattern | Category | Example |
|---------|----------|---------|
| `*gc*bias*` | GC Bias Plot | `subject_001_gc_bias.pdf` |
| `*base*distribution*cycle*` | Base Distribution Plot | `base_distribution_by_cycle.pdf` |
| `*insert*size*` | Insert Size Histogram | `insert_size_histogram.pdf` |
| `*quality*cycle*` | Quality by Cycle Plot | `quality_by_cycle.pdf` |
| `*quality*distribution*` | Quality Distribution Plot | `quality_distribution.pdf` |

### TXT Files
| Pattern | Category | DataType | Example |
|---------|----------|----------|---------|
| `*haplotype*call*` | Haplotype Calls | `variant_calls` | `haplotype_calls.txt.gz` |
| `*summary*`, `*repeat*`, `*genotype*` | Summary Table | `genomicVariants` | `repeat_summary.txt` |

## What Metadata Gets Added?

For matched files, the system automatically adds:

1. **Title**: Descriptive name with subject ID (if present)
   - Example: `GC Bias QC Plot - subject_123`

2. **Description**: Detailed explanation (< 500 chars)
   - Example: "Quality control plot showing GC content bias across the sequence..."

3. **Keywords**: Relevant tags for searchability
   - Example: `['qc', 'quality_control', 'gc_bias', 'sequencing_qc', 'plot']`

4. **DataType**: For haplotype calls and summary tables
   - Haplotype calls → `variant_calls`
   - Summary tables → `genomicVariants`

5. **FileFormat**: Standard format tags
   - PDF → `PDF`
   - TXT → `TXT`
   - TBI → `TBI` (index files)

## How to Use

### With generate-file-templates Command

```bash
python synapse_dataset_manager.py generate-file-templates \
  --folder syn123456 \
  --mapping mapping/target_als_test.json \
  --output annotations/file_annotations.json
```

The enrichment happens automatically! No special flags needed.

### In Python Code

```python
from synapse_dataset_manager import enrich_metadata_with_file_info

# Minimal metadata
metadata = {
    'gs_uri': 'gs://bucket/subject_123_gc_bias.pdf'
}

# Enrich
enriched = enrich_metadata_with_file_info(metadata)

# Access computed fields
print(enriched['_computed_title'])
# Output: "GC Bias QC Plot - subject_123"

print(enriched['_computed_keywords'])
# Output: ['qc', 'quality_control', 'gc_bias', 'sequencing_qc', 'plot']
```

## Subject ID Extraction

The system automatically extracts subject IDs from filenames to make titles more specific:

### Supported Patterns

1. **subject_XXX**: `subject_001_gc_bias.pdf` → "GC Bias QC Plot - subject_001"
2. **subject-XXX**: `subject-123-quality.pdf` → "Quality by Cycle QC Plot - subject-123"
3. **ALPHANUMERIC**: `ABCD1234_summary.txt` → "Repeat Expansion Summary Table - ABCD1234"

### Case Handling

- Case insensitive for "subject" prefix
- Preserves original case for alphanumeric IDs
- Requires 6+ characters for generic alphanumeric IDs

## Keyword Merging

If a file template already has keywords, computed keywords are **merged** (not replaced):

```python
# Template has existing keywords
template = {
    'keywords': ['manual_tag', 'important']
}

# After enrichment and filling
result = {
    'keywords': ['manual_tag', 'important', 'qc', 'quality_control', 'gc_bias']
}
```

Duplicates are automatically removed.

## Files That Don't Match

Files that don't match any pattern still process normally:

- Extension and file format are still detected
- No category-specific metadata is added
- No errors or warnings
- Ready for manual annotation

Example:
```python
metadata = {'gs_uri': 'random_document.pdf'}
enriched = enrich_metadata_with_file_info(metadata)

# Result:
{
    '_file_extension': 'pdf',
    '_computed_fileFormat': 'PDF'
    # No _file_category, _computed_title, etc.
}
```

## Mapping Configuration

The mapping file (`mapping/target_als_test.json`) controls how computed fields map to schema fields:

```json
{
  "_file_category": {
    "target": "",
    "values": {}
  },
  "_computed_title": "title",
  "_computed_description": "description",
  "_computed_keywords": "keywords"
}
```

- `_file_category`: Metadata only, not written to annotations
- Other fields map directly to schema fields

## Testing

Verify the categorization system:

```bash
# Run unit tests
python -m pytest test_file_categorization.py -v

# Run integration tests
python test_integration_categorization.py

# See demo with examples
python demo_categorization.py
```

## Troubleshooting

### File not getting categorized?

Check the pattern:
```python
from synapse_dataset_manager import extract_file_category

category = extract_file_category('your_file.pdf')
print(category)  # Should show category or None
```

### Subject ID not extracted?

The regex requires:
- `subject_XXX` or `subject-XXX` pattern, OR
- 6+ character alphanumeric code with both letters and numbers

### Keywords not merging?

Verify the mapping file has:
```json
"_computed_keywords": "keywords"
```

## Pattern Reference

### Regex Patterns Used

```python
{
    'gc_bias_plot': r'gc[_-]?bias',
    'base_distribution_plot': r'base[_-]?distribution[_-]?by[_-]?cycle',
    'insert_size_histogram': r'insert[_-]?size',
    'quality_by_cycle_plot': r'quality[_-]?by[_-]?cycle',
    'quality_distribution_plot': r'quality[_-]?distribution',
    'haplotype_calls': r'haplotype[_-]?calls?',
    'summary_table': r'summary|repeat[_-]?id|repeat[_-]?unit|target[_-]?region|genotype',
}
```

### Adding New Patterns

Edit `get_file_category_patterns()` in `synapse_dataset_manager.py`:

```python
def get_file_category_patterns() -> Dict[str, str]:
    return {
        # Existing patterns...

        # Add your new pattern
        'new_category': r'pattern[_-]?regex',
    }
```

Then add corresponding entries to:
- `generate_title_from_category()`
- `generate_description_from_category()`
- `generate_keywords_from_category()`
- `get_datatype_from_category()` (if needed)

## Examples

### Example 1: QC Plot with Subject ID

```
Input:  subject_123_gc_bias.pdf
Output:
  title: "GC Bias QC Plot - subject_123"
  description: "Quality control plot showing GC content bias..."
  keywords: ['qc', 'quality_control', 'gc_bias', 'sequencing_qc', 'plot']
  fileFormat: 'PDF'
```

### Example 2: Haplotype Calls

```
Input:  haplotype_calls.txt.gz
Output:
  title: "Haplotype Calls"
  description: "Variant haplotype calls from whole genome sequencing..."
  keywords: ['variant_calls', 'haplotype', 'genomics', 'vcf', 'phased_variants']
  dataType: 'variant_calls'
  fileFormat: 'TXT'
```

### Example 3: Summary Table with ID

```
Input:  ABCD1234_repeat_expansion_summary.txt
Output:
  title: "Repeat Expansion Summary Table - ABCD1234"
  description: "Summary table containing repeat expansion analysis results..."
  keywords: ['repeat_expansion', 'summary', 'genotype', 'genomics', 'c9orf72', 'atxn2']
  dataType: 'genomicVariants'
  fileFormat: 'TXT'
```

## Support

For issues or questions:
1. Check the implementation summary: `CATEGORIZATION_IMPLEMENTATION.md`
2. Review test cases: `test_file_categorization.py`
3. Run the demo: `python demo_categorization.py`
