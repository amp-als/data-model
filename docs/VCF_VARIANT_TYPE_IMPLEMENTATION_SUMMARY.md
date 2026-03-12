# VCF Variant Type Detection - Implementation Summary

## Overview

Successfully implemented automatic variant type detection for VCF files based on folder structure. The system now automatically enriches VCF annotations with:
- **variantType** field (Genomic, Small_Variant, Structural_Variant, Repeat_Expansion)
- Specific **dataType** overrides (StructuralVariants, GermlineVariants, genomicVariants)
- Variant-specific **keywords** for discoverability

## Implementation Status

✅ **All 10 tasks completed successfully**

### Changes Made

#### 1. Schema Updates

**File: `modules/clinical/genetic-profile.yaml`**
- Added 3 new enum values to VariantTypeEnum:
  - `Genomic`: All variant types from genome-wide haplotype calling
  - `Small_Variant`: Small variants (SNVs and InDels)
  - `Structural_Variant`: Structural variants (DEL, INS, DUP, INV, CNVs)

**File: `modules/datasets/OmicFile.yaml`**
- Added `variantType` field with VariantTypeEnum range
- Field is optional and specific to VCF files

**File: `json-schemas/OmicFile.json`**
- Regenerated to include variantType field

#### 2. Detection Functions

**File: `synapse_dataset_manager.py`**

Added 4 new functions (lines 1069-1192):

1. **`extract_variant_type_from_path(folder_path)`**
   - Detects variant type from folder structure
   - Supports: structural, small, genomic, repeat-expansion folders
   - Case insensitive with priority ordering

2. **`map_variant_type_to_enum(variant_type)`**
   - Maps internal IDs to VariantTypeEnum values
   - Returns: Structural_Variant, Small_Variant, Genomic, Repeat_Expansion

3. **`map_variant_type_to_datatype(variant_type)`**
   - Maps variant type to specific OmicDataTypeEnum values
   - structural → StructuralVariants
   - small → GermlineVariants
   - genomic/repeat_expansion → genomicVariants

4. **`generate_variant_type_keywords(variant_type)`**
   - Generates search keywords based on variant type
   - structural → ['structural_variants', 'cnv', 'copy_number', ...]
   - small → ['small_variants', 'snv', 'indel', 'germline', ...]
   - genomic → ['genomic_variants', 'haplotype', 'variant_calls', ...]
   - repeat_expansion → ['repeat_expansion', 'c9orf72', 'atxn2', ...]

#### 3. Enrichment Integration

**Updated `enrich_metadata_with_file_info()` function:**
- Added `folder_path` parameter (optional, backward compatible)
- Updated docstring to document new computed fields
- Added VCF detection logic block (lines 1286-1307):
  - Only triggers for extension=='vcf' AND folder_path provided
  - Stores debug field: `_variant_type_detected`
  - Computes: `_computed_variantType`
  - Overrides: `_computed_dataType`
  - Generates: `_computed_keywords`

**Updated 3 call sites in `handle_generate_file_templates()`:**
- Line 3629: Extracts folder_path and passes to enrichment function
- Line 3636: Same for no-metadata-match case
- Line 3641: Same for no-metadata-file case

#### 4. Mapping Configuration

**File: `mapping/target_als_test.json`**
- Added mapping: `"_computed_variantType": "variantType"`
- Maps computed field to output annotation field

#### 5. Testing

**Created `test_variant_type_detection.py`**
- 44 comprehensive unit tests covering:
  - Path parsing (13 tests)
  - Enum mapping (7 tests)
  - DataType mapping (6 tests)
  - Keyword generation (7 tests)
  - Integration with enrichment function (11 tests)
- **All 44 tests passing ✅**

**Verified no regression:**
- Ran existing `test_file_categorization.py`
- **All 43 existing tests still passing ✅**

**Created `verify_variant_type_detection.py`**
- Integration verification script for generated annotations
- Validates:
  - VCF files get correct variantType
  - DataType overridden correctly
  - Keywords populated
  - Non-VCF files unaffected
  - VCF index files (.tbi) have no variantType

## Folder Structure → Annotation Mappings

| Folder Pattern | variantType | dataType | Keywords |
|----------------|-------------|----------|----------|
| `*/structural/*` | Structural_Variant | StructuralVariants | structural_variants, cnv, copy_number, deletions, duplications |
| `*/small/*` | Small_Variant | GermlineVariants | small_variants, snv, indel, germline |
| `*/genomic/*` | Genomic | genomicVariants | genomic_variants, haplotype, variant_calls |
| `*/repeat-expansion/*` | Repeat_Expansion | genomicVariants | repeat_expansion, c9orf72, atxn2, repeat_analysis |

## Edge Cases Handled

✅ **VCF index files (.vcf.gz.tbi)**: Extension = 'tbi', not 'vcf' → no variant type assigned
✅ **VCF files outside variant folders**: No folder_path or no match → generic genomicVariants
✅ **Non-VCF files in variant folders**: Extension check prevents assignment
✅ **Case insensitivity**: Handles "STRUCTURAL", "Structural", "structural"
✅ **Missing folder_path**: Parameter optional, backward compatible
✅ **Multiple folder names**: Priority order (repeat-expansion > structural > small > genomic)
✅ **Parameter priority**: Explicit folder_path takes precedence over metadata values

## Testing with Real Data

### Generate Annotations

```bash
conda activate amp-als

python synapse_dataset_manager.py generate-file-templates \
  --folder syn73810738 \
  --type Omic \
  --mapping mapping/target_als_test.json \
  --metadata downloads/Target_ALS/metadata/ \
  --output annotations/vcf_variant_test.json
```

### Verify Results

```bash
python verify_variant_type_detection.py annotations/vcf_variant_test.json
```

### Spot Check

```bash
python -c "
import json
with open('annotations/vcf_variant_test.json', 'r') as f:
    data = json.load(f)

for syn_id, files in list(data.items())[:50]:
    for filename, annots in files.items():
        if '.vcf.gz' in filename and not filename.endswith('.tbi'):
            if annots.get('variantType') == 'Structural_Variant':
                print(f'File: {filename}')
                print(f'  variantType: {annots.get(\"variantType\")}')
                print(f'  dataType: {annots.get(\"dataType\")}')
                print(f'  keywords: {annots.get(\"keywords\", [])}')
                break
"
```

Expected output:
```
File: SUBJECT001.structural.vcf.gz
  variantType: Structural_Variant
  dataType: ['StructuralVariants']
  keywords: ['structural_variants', 'cnv', 'copy_number', 'deletions', 'duplications', 'genomics', 'vcf']
```

## Files Created/Modified

### Modified Files (8)
1. `modules/clinical/genetic-profile.yaml` - Added 3 enum values
2. `modules/datasets/OmicFile.yaml` - Added variantType field
3. `json-schemas/OmicFile.json` - Regenerated with variantType
4. `synapse_dataset_manager.py` - Added 4 functions + enrichment logic
5. `mapping/target_als_test.json` - Added variantType mapping

### New Files (2)
6. `test_variant_type_detection.py` - 44 unit tests
7. `verify_variant_type_detection.py` - Verification script

## Success Criteria

✅ New VariantTypeEnum values added (Genomic, Small_Variant, Structural_Variant)
✅ variantType field in OmicFile schema
✅ All 4 detection functions implemented
✅ VCF detection logic in enrich_metadata_with_file_info()
✅ All 3 call sites updated
✅ Mapping configuration updated
✅ 44 unit tests passing
✅ No regression in existing 43 tests
✅ Verification script created

## Next Steps

1. **Test with real Synapse data** - Run generate-file-templates on syn73810738
2. **Verify annotations** - Run verify_variant_type_detection.py on output
3. **Spot check results** - Manually verify VCFs in each variant folder
4. **Upload annotations** - Use annotate-dataset command to apply to Synapse

## Benefits

1. **Better Discoverability**: Users can filter VCFs by variant type in Synapse
2. **Accurate Metadata**: DataType reflects actual content (StructuralVariants vs GermlineVariants)
3. **Automated Enrichment**: No manual annotation needed for 1200+ VCF files
4. **Consistent Taxonomy**: Follows existing schema patterns and OmicDataTypeEnum values
5. **Backward Compatible**: Existing functionality preserved, new features optional

## Design Patterns Followed

- ✅ **Parameter Priority Pattern**: Explicit parameters > metadata values (per MEMORY.md)
- ✅ **Extension Pattern**: Follows existing PDF/TXT categorization system
- ✅ **Backward Compatibility**: New folder_path parameter is optional
- ✅ **Separation of Concerns**: Detection logic separate from enrichment
- ✅ **Comprehensive Testing**: Unit tests + integration tests + verification script
