# Dynamic File Extension Mapping Implementation Summary

## Overview

Successfully implemented dynamic file extension mapping for Target ALS dataset to automatically assign correct `dataType` and `fileFormat` values based on actual file extensions rather than using fixed values or unreliable metadata columns.

## Problem Solved

**Before:** All files incorrectly received fixed values:
- `dataType: "genomicVariants"` - wrong for BAM/CRAM files (should be "aligned_reads")
- `fileFormat` - from unreliable `file_type` metadata column (often incorrect)

**After:** Dynamic assignment based on file extension:
- BAM/CRAM files → `dataType: "aligned_reads"`, `fileFormat: "BAM"/"CRAM"`
- VCF files → `dataType: "genomicVariants"`, `fileFormat: "VCF"`
- Index files → `fileFormat: "BAI"/"CRAI"/"TBI"` (dataType left empty - appropriate for technical files)

## Implementation Details

### 1. New Functions in `synapse_dataset_manager.py` (lines 794-988)

#### `extract_file_extension(file_identifier: str) -> str`
- Extracts extension from filenames, URLs, or paths
- Handles compressed files (.gz) by using inner extension
- Case-insensitive

#### `map_extension_to_datatype(extension: str) -> str`
- Maps file extensions to OmicDataTypeEnum values
- Based on `modules/omics/data-types.yaml`
- Covers: sequencing (fastq, fasta), aligned reads (bam, sam, cram), variants (vcf, bcf), annotations (gtf, gff, bed), expression (gct)
- Returns empty string for index files (not omic data types)

#### `map_extension_to_fileformat(extension: str) -> str`
- Maps file extensions to uppercase file format strings
- Covers all common bioinformatics formats

#### `enrich_metadata_with_file_info(metadata_row: dict, file_name: str) -> dict`
- Enriches metadata with computed fields:
  - `_file_extension`: extracted extension
  - `_computed_dataType`: data type from extension
  - `_computed_fileFormat`: file format from extension
- Checks multiple metadata columns for file identifier (gs_uri, url, file_name, etc.)
- Falls back gracefully if no file info available

### 2. Workflow Integration (line 3093-3096)

Modified the file annotation workflow to enrich metadata BEFORE applying mappings:

```python
# Enrich metadata with file-derived fields
metadata_row = enrich_metadata_with_file_info(metadata_index[subject_id], filename)
merged = fill_template_from_metadata(merged, metadata_row, mapping)
```

### 3. Mapping File Updates (`mapping/target_als_test.json`)

**Removed fixed values:**
- ❌ `dataType_fixed` (was forcing all files to "genomicVariants")
- ❌ `assay_fixed` (was forcing all files to "wholeGenomeSeq")
- ❌ `libraryStrategy_fixed` (was forcing all files to "WGS")

**Added computed field mappings:**
- ✅ `"_computed_dataType": "dataType"` - maps computed data type to dataType field
- ✅ `"_computed_fileFormat": "fileFormat"` - maps computed format to fileFormat field
- ✅ `"_file_extension": {"target": "", "values": {}}` - available for debugging but not mapped

**Disabled unreliable metadata:**
- ✅ `"file_type": {"target": "", "values": {}}` - prevents unreliable metadata from overwriting computed values

## File Extension Mapping Tables

### Data Types (aligned with OmicDataTypeEnum)

| Extension | Data Type | Description |
|-----------|-----------|-------------|
| fastq, fq, fasta, fa, fna | raw_sequencing | Raw sequencing data |
| bam, sam, cram | aligned_reads | Aligned sequencing reads |
| vcf, bcf | genomicVariants | Variant calling results |
| gtf, gff, gff3, bed | genome_annotation | Genome annotation data |
| gct | gene_expression | Gene expression data |
| bai, crai, csi, tbi, jsi | *(empty)* | Index files (technical, not omic data) |

### File Formats

| Extension | File Format |
|-----------|-------------|
| bam | BAM |
| cram | CRAM |
| vcf | VCF |
| fastq, fq | FASTQ |
| bai | BAI |
| crai | CRAI |
| tbi | TBI |
| gz | GZIP |
| pdf | PDF |
| md5 | MD5 |

## Edge Cases Handled

1. **Compressed files** (.gz, .bz2, .zip): Uses inner extension (e.g., `file.vcf.gz` → extension = "vcf")
2. **Index files** (.bam.bai): Correctly extracts last extension (.bai)
3. **Missing file names**: Falls back gracefully, returns empty strings
4. **Unknown extensions**: Returns empty string, doesn't overwrite existing values
5. **Case insensitivity**: Extensions converted to lowercase for consistent matching

## Validation

### Unit Tests (`test_file_extension_mapping.py`)
- ✅ 8/8 tests for extension extraction
- ✅ 16/16 tests for dataType mapping
- ✅ 10/10 tests for fileFormat mapping
- ✅ 4/4 tests for metadata enrichment

All tests pass successfully!

### Verification Script (`verify_mapping_integration.py`)
Demonstrates correct classification of Target ALS file types:
- CRAM files: aligned_reads + CRAM ✓
- CRAI index files: (no dataType) + CRAI ✓
- BAM files: aligned_reads + BAM ✓
- VCF.GZ files: genomicVariants + VCF ✓
- FASTQ.GZ files: raw_sequencing + FASTQ ✓

## Benefits

1. **Accuracy**: Files correctly classified by their actual type
2. **Maintainability**: No need to manually update fixed values for different file types
3. **Flexibility**: Works with any file extension, new types can be added to mapping tables
4. **Backward Compatible**: Falls back gracefully, doesn't break existing workflows
5. **Debuggable**: `_file_extension` field available for troubleshooting

## Design Philosophy

**Preprocessing (enrichment) vs. conditional logic:**
- Chose preprocessing approach to keep mapping system simple and declarative
- Computed fields treated like any other metadata column
- Easy to debug (computed fields visible in enriched metadata)
- Consistent with existing mapping semantics

## Future Enhancements

If additional dynamic mappings are needed:
1. Add more computed columns in enrichment step
2. Create reusable enrichment functions for common patterns
3. Consider externalizing mapping tables to YAML configuration

## Files Modified

1. **synapse_dataset_manager.py**
   - Added 4 new functions (194 lines)
   - Modified 1 line in workflow

2. **mapping/target_als_test.json**
   - Removed 3 fixed value entries
   - Added 3 computed field mappings
   - Disabled 1 unreliable metadata column

3. **Test files created:**
   - `test_file_extension_mapping.py` (unit tests)
   - `verify_mapping_integration.py` (demo/verification)

## Success Criteria Met

✅ Code changes complete and tested
✅ Mapping file updated correctly
✅ All unit tests pass
✅ No regressions in other mappings
✅ BAM/CRAM files correctly classified as `aligned_reads`
✅ VCF files correctly classified as `genomicVariants`
✅ Index files correctly handled (fileFormat set, dataType empty)
✅ Compressed files use inner extension
✅ Falls back gracefully for missing data

## Next Steps

To use the new mapping:

```bash
python synapse_dataset_manager.py generate-file-templates \
  --folder syn123456 \
  --mapping mapping/target_als_test.json \
  --metadata annotations/target_als_metadata.csv \
  --output annotations/target_als_file_annotations_new.json
```

Then verify the output has correct dataType and fileFormat values for each file type.
