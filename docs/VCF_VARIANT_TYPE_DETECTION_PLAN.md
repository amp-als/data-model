# Implementation Plan: VCF Variant Type Detection

## Overview

Add variant type detection for VCF files based on folder structure, extending the schema with a variantType field, overriding dataType with specific values, and generating variant-type keywords for enhanced discoverability.

## The 4 Enhancements

1. **Variant Type Detection**: Parse folder names to detect variant types
2. **DataType Override**: Use specific dataTypes (StructuralVariants, GermlineVariants, etc.)
3. **Keyword Generation**: Add variant-type specific keywords
4. **Schema Extension**: Add variantType field to OmicFile

## User's Folder Structure

- `genomic`: Haplotype calls for all types of variants
- `repeat-expansion`: Repeat-expansion VCFs
- `small`: Small variant VCFs
- `structural`: Structural variant VCFs

## Variant Type Mappings

| Folder Name | VariantTypeEnum | OmicDataTypeEnum | Description |
|-------------|-----------------|------------------|-------------|
| `structural` | `CNV` | `StructuralVariants` | Structural variants, CNVs, SVs |
| `repeat-expansion` | `Repeat_Expansion` | `genomicVariants` | Repeat expansions (C9orf72, etc.) |
| `small` | `Indel` | `GermlineVariants` | Small variants (SNVs + Indels) |
| `genomic` | `SNV` | `genomicVariants` | Generic/all variant types |

---

## Phase 1: Schema Foundation

### Step 1.1: Add VariantTypeEnum to Common Enums

**File**: `/home/ramayyala/github/data-model/modules/shared/common-enums.yaml`

**Location**: After LibraryLayoutEnum (around line 48), before Disease classifications

**Add**:
```yaml
  # Variant types for genomic data
  VariantTypeEnum:
    description: Type of genetic variant
    permissible_values:
      SNV:
        description: Single nucleotide variant
      Indel:
        description: Insertion or deletion variant
      CNV:
        description: Copy number variant
      Repeat_Expansion:
        description: Repeat expansion (e.g., C9orf72)
      Other:
        description: Other variant type
```

**Rationale**: Moving VariantTypeEnum from `genetic-profile.yaml` to `common-enums.yaml` makes it reusable across both clinical and omic contexts.

### Step 1.2: Add variantType Field to OmicFile Schema

**File**: `/home/ramayyala/github/data-model/modules/datasets/OmicFile.yaml`

**Location**: After `fileFormat` field (line 42), before `sampleIdColumn` (line 44)

**Add**:
```yaml
      # Variant type classification
      variantType:
        title: Variant Type
        range: VariantTypeEnum
        description: Type of genetic variant for VCF files (SNV, Indel, CNV, Repeat_Expansion)
        required: false
```

### Step 1.3: Regenerate JSON Schema

**Commands**:
```bash
cd /home/ramayyala/github/data-model
make OmicFile
```

**Verify**:
```bash
grep -A 5 "variantType" json-schemas/OmicFile.json
```

**Expected output**:
```json
"variantType": {
  "title": "Variant Type",
  "type": "string",
  "description": "Type of genetic variant for VCF files",
  "enum": ["SNV", "Indel", "CNV", "Repeat_Expansion", "Other"]
}
```

---

## Phase 2: Core Detection Logic

### Step 2.1: Add Variant Type Detection Functions

**File**: `/home/ramayyala/github/data-model/synapse_dataset_manager.py`

**Location**: After `get_datatype_from_category()` function (around line 1067)

#### Function 1: Extract Variant Type from Folder Path

```python
def extract_variant_type_from_path(folder_path: str) -> Optional[str]:
    """
    Detect variant type from folder path structure.

    Looks for specific folder names in the path:
    - 'genomic' → 'genomic' (all variant types)
    - 'repeat-expansion' or 'repeat_expansion' → 'Repeat_Expansion'
    - 'small' → 'small' (SNVs and indels)
    - 'structural' → 'CNV'

    Args:
        folder_path: Folder path string (e.g., "wgs/vcf/structural/SUBJECT001")

    Returns:
        Variant type identifier string, or None if no match

    Example:
        >>> extract_variant_type_from_path("wgs/vcf/structural/SUBJECT001")
        'CNV'
        >>> extract_variant_type_from_path("wgs/vcf/repeat-expansion/SUBJECT002")
        'Repeat_Expansion'
    """
    if not folder_path:
        return None

    # Normalize path and convert to lowercase for matching
    path_lower = folder_path.lower()
    path_parts = [p.strip() for p in path_lower.split('/') if p.strip()]

    # Pattern matching: check for specific folder names
    # Order matters: more specific patterns first
    if 'repeat-expansion' in path_parts or 'repeat_expansion' in path_parts:
        return 'Repeat_Expansion'
    elif 'structural' in path_parts:
        return 'CNV'
    elif 'small' in path_parts:
        return 'small'
    elif 'genomic' in path_parts:
        return 'genomic'

    return None
```

#### Function 2: Map Variant Type to VariantTypeEnum

```python
def map_variant_type_to_enum(variant_type: str) -> Optional[str]:
    """
    Map internal variant type identifier to VariantTypeEnum value.

    Args:
        variant_type: Internal identifier from folder structure

    Returns:
        VariantTypeEnum value, or None if unmapped

    Example:
        >>> map_variant_type_to_enum('CNV')
        'CNV'
        >>> map_variant_type_to_enum('small')
        'Indel'
    """
    if not variant_type:
        return None

    variant_type_map = {
        'CNV': 'CNV',
        'Repeat_Expansion': 'Repeat_Expansion',
        'small': 'Indel',  # Small variants = SNVs + Indels, default to Indel
        'genomic': 'SNV',  # Genomic folder contains all types, default to SNV
    }

    return variant_type_map.get(variant_type)
```

#### Function 3: Map Variant Type to Specific DataType

```python
def map_variant_type_to_datatype(variant_type: str) -> Optional[str]:
    """
    Map variant type to specific OmicDataTypeEnum value.

    Overrides generic 'genomicVariants' with more specific types:
    - CNV → 'StructuralVariants'
    - Repeat_Expansion → 'genomicVariants' (no more specific type)
    - small → 'GermlineVariants'
    - genomic → 'genomicVariants' (generic)

    Args:
        variant_type: Internal variant type identifier

    Returns:
        OmicDataTypeEnum value, or None if no override needed
    """
    if not variant_type:
        return None

    datatype_map = {
        'CNV': 'StructuralVariants',
        'Repeat_Expansion': 'genomicVariants',
        'small': 'GermlineVariants',
        'genomic': 'genomicVariants',
    }

    return datatype_map.get(variant_type)
```

#### Function 4: Generate Variant Type Keywords

```python
def generate_variant_type_keywords(variant_type: str) -> List[str]:
    """
    Generate keywords based on variant type for enhanced discoverability.

    Args:
        variant_type: Internal variant type identifier

    Returns:
        List of relevant keywords
    """
    if not variant_type:
        return []

    keyword_map = {
        'CNV': [
            'structural_variants',
            'cnv',
            'copy_number',
            'deletions',
            'duplications',
            'genomics',
            'vcf'
        ],
        'Repeat_Expansion': [
            'repeat_expansion',
            'c9orf72',
            'atxn2',
            'repeat_analysis',
            'genomics',
            'vcf'
        ],
        'small': [
            'small_variants',
            'snv',
            'indel',
            'germline',
            'genomics',
            'vcf'
        ],
        'genomic': [
            'genomic_variants',
            'haplotype',
            'variant_calls',
            'genomics',
            'vcf'
        ],
    }

    return keyword_map.get(variant_type, [])
```

---

## Phase 3: Integration into Enrichment Pipeline

### Step 3.1: Update Function Signature

**File**: `/home/ramayyala/github/data-model/synapse_dataset_manager.py`

**Location**: Line 1069 (enrich_metadata_with_file_info function)

**Change signature from**:
```python
def enrich_metadata_with_file_info(metadata_row: dict, file_name: str = None) -> dict:
```

**To**:
```python
def enrich_metadata_with_file_info(metadata_row: dict, file_name: str = None, folder_path: str = None) -> dict:
```

**Update docstring** (lines 1082-1088):
```python
    Args:
        metadata_row: Original metadata dictionary
        file_name: Optional file name to use for enrichment.
                   IMPORTANT: If provided, this takes PRIORITY over any
                   file paths in metadata_row to avoid using stale/polluted
                   values from metadata merging.
        folder_path: Optional folder path for variant type detection.
                     Used to extract variant type from folder structure
                     (e.g., "wgs/vcf/structural/SUBJECT001").

    Returns:
        Enriched metadata dictionary with computed fields
```

### Step 3.2: Add VCF Variant Detection Logic

**File**: `/home/ramayyala/github/data-model/synapse_dataset_manager.py`

**Location**: After line 1152 (after the category-based enrichment block for PDF/TXT)

**Add**:
```python
    # VCF Variant Type Detection (add after line 1152)
    if extension == 'vcf' and folder_path:
        variant_type = extract_variant_type_from_path(folder_path)

        if variant_type:
            # Store the internal variant type identifier (for debugging/logging)
            enriched['_variant_type_detected'] = variant_type

            # Map to VariantTypeEnum value
            variant_enum = map_variant_type_to_enum(variant_type)
            if variant_enum:
                enriched['_computed_variantType'] = variant_enum

            # Override dataType with specific value
            specific_datatype = map_variant_type_to_datatype(variant_type)
            if specific_datatype:
                enriched['_computed_dataType'] = specific_datatype

            # Generate variant-type keywords
            variant_keywords = generate_variant_type_keywords(variant_type)
            if variant_keywords:
                enriched['_computed_keywords'] = variant_keywords

    return enriched
```

### Step 3.3: Update Function Call Sites

**File**: `/home/ramayyala/github/data-model/synapse_dataset_manager.py`

Update all 3 call sites to pass `folder_path` parameter:

#### Call Site 1: Line 3472
**Change from**:
```python
metadata_row = enrich_metadata_with_file_info(metadata_index[subject_id], filename)
```

**To**:
```python
folder_path = file_info.get('path', '')
metadata_row = enrich_metadata_with_file_info(metadata_index[subject_id], filename, folder_path)
```

#### Call Site 2: Line 3479
**Change from**:
```python
metadata_row = enrich_metadata_with_file_info({}, filename)
```

**To**:
```python
folder_path = file_info.get('path', '')
metadata_row = enrich_metadata_with_file_info({}, filename, folder_path)
```

#### Call Site 3: Line 3483
**Change from**:
```python
metadata_row = enrich_metadata_with_file_info({}, filename)
```

**To**:
```python
folder_path = file_info.get('path', '')
metadata_row = enrich_metadata_with_file_info({}, filename, folder_path)
```

---

## Phase 4: Mapping Configuration

### Step 4.1: Update Mapping File

**File**: `/home/ramayyala/github/data-model/mapping/target_als_test.json`

**Add computed field mappings** (merge into existing JSON):
```json
{
  "_computed_variantType": "variantType",
  "_computed_dataType": "dataType",
  "_computed_keywords": "keywords"
}
```

**Note**: The `_computed_dataType` and `_computed_keywords` mappings may already exist. Ensure they're present and not duplicated.

---

## Phase 5: Testing & Validation

### Step 5.1: Create Unit Tests

**File**: `/home/ramayyala/github/data-model/test_variant_type_detection.py` (NEW)

Create comprehensive test file with 30+ tests covering:
- Variant type extraction from folder paths
- Enum mapping
- DataType override
- Keyword generation
- Integration with enrichment function
- Edge cases

**Key test classes**:
- `TestVariantTypeExtraction`: Test folder path parsing
- `TestEnumMapping`: Test variant type to enum mapping
- `TestDataTypeOverride`: Test dataType override logic
- `TestKeywordGeneration`: Test keyword generation
- `TestEnrichmentIntegration`: Test full enrichment pipeline
- `TestEdgeCases`: Test edge cases and error handling

### Step 5.2: Run Unit Tests

**Commands**:
```bash
cd /home/ramayyala/github/data-model
python -m pytest test_variant_type_detection.py -v
```

**Expected**: All tests pass ✅

### Step 5.3: Run Existing Tests

**Commands**:
```bash
python -m pytest test_file_categorization.py -v
```

**Expected**: All 43 existing tests continue to pass (no regression) ✅

### Step 5.4: Integration Test with Real Data

**Commands**:
```bash
# Test with actual Synapse folder (if available)
python synapse_dataset_manager.py generate-file-templates \
  --folder syn73810834 \
  --type Omic \
  --mapping mapping/target_als_test.json \
  --metadata downloads/Target_ALS/metadata/ \
  --output annotations/vcf_variant_detection_test.json
```

**Verify**:
```bash
# Check structural variant VCFs
python3 -c "
import json
with open('annotations/vcf_variant_detection_test.json', 'r') as f:
    data = json.load(f)

for folder_id, files in data.items():
    for filename, annots in files.items():
        if '.vcf' in filename and 'structural' in folder_id.lower():
            print(f'File: {filename}')
            print(f'  variantType: {annots.get(\"variantType\", \"N/A\")}')
            print(f'  dataType: {annots.get(\"dataType\", \"N/A\")}')
            print(f'  keywords: {annots.get(\"keywords\", [])}')
            print()
            break
"
```

**Expected output**:
```
File: sample.vcf.gz
  variantType: CNV
  dataType: ['StructuralVariants']
  keywords: ['structural_variants', 'cnv', 'copy_number', ...]
```

---

## Implementation Sequence

Execute in this order to minimize integration issues:

### ✅ Phase 1: Schema Foundation
1. Add VariantTypeEnum to `common-enums.yaml`
2. Add variantType field to `OmicFile.yaml`
3. Run `make OmicFile` to regenerate JSON schema
4. Verify schema compilation

### ✅ Phase 2: Core Detection Logic
5. Add 4 detection functions to `synapse_dataset_manager.py`:
   - `extract_variant_type_from_path()`
   - `map_variant_type_to_enum()`
   - `map_variant_type_to_datatype()`
   - `generate_variant_type_keywords()`

### ✅ Phase 3: Integration
6. Update `enrich_metadata_with_file_info()` signature (add folder_path)
7. Add VCF variant detection logic to enrichment function
8. Update all 3 call sites to pass folder_path parameter

### ✅ Phase 4: Mapping Configuration
9. Update `mapping/target_als_test.json` with computed field mappings

### ✅ Phase 5: Testing & Validation
10. Create `test_variant_type_detection.py` with comprehensive tests
11. Run unit tests and verify passing
12. Run existing tests to verify no regression
13. Test with real Synapse data

---

## Edge Cases & Considerations

### 1. VCF Index Files (.vcf.gz.tbi)
- Will be detected as extension 'tbi' (not 'vcf')
- Variant type detection won't trigger ✅
- Index files don't need variant type metadata ✅

### 2. VCF Files Outside Expected Folders
- Detection returns None if folder doesn't match patterns ✅
- Falls back to generic 'genomicVariants' dataType ✅
- No variantType field populated ✅

### 3. Multiple Variant Folder Names in Path
- Function checks in priority order:
  - `repeat-expansion` (most specific)
  - `structural`
  - `small`
  - `genomic` (least specific)
- First match wins ✅

### 4. Case Sensitivity
- Folder matching is case-insensitive ✅
- Handles "STRUCTURAL", "Structural", "structural" equally ✅

### 5. Backward Compatibility
- New folder_path parameter is optional (defaults to None) ✅
- Existing code without folder_path continues working ✅
- Only VCF files in recognized folders get variant detection ✅

### 6. Keyword Merging
- Variant keywords are merged with existing keywords ✅
- Deduplication happens in `fill_template_from_metadata()` ✅
- Preserves manually added keywords ✅

---

## Success Criteria

All criteria must be met before considering implementation complete:

- [ ] VariantTypeEnum added to common-enums.yaml
- [ ] variantType field added to OmicFile.yaml
- [ ] OmicFile JSON schema regenerated successfully
- [ ] All 4 detection functions implemented in synapse_dataset_manager.py
- [ ] enrich_metadata_with_file_info() updated with VCF detection logic
- [ ] All 3 call sites updated to pass folder_path
- [ ] Mapping file updated with computed field mappings
- [ ] test_variant_type_detection.py created with 30+ tests
- [ ] All unit tests passing
- [ ] All existing tests passing (no regression)
- [ ] Variant type correctly detected for all 4 folder patterns
- [ ] DataType override working (StructuralVariants, GermlineVariants, etc.)
- [ ] Keywords generated and merged correctly
- [ ] Non-VCF files unaffected by new logic
- [ ] VCF files outside recognized folders handled gracefully

---

## Files to Modify

| File | Changes | Priority |
|------|---------|----------|
| `modules/shared/common-enums.yaml` | Add VariantTypeEnum | High |
| `modules/datasets/OmicFile.yaml` | Add variantType field | High |
| `synapse_dataset_manager.py` | Add 4 detection functions | High |
| `synapse_dataset_manager.py` | Update enrich_metadata_with_file_info() | High |
| `synapse_dataset_manager.py` | Update 3 call sites | High |
| `mapping/target_als_test.json` | Add computed field mappings | Medium |
| `test_variant_type_detection.py` (NEW) | Create comprehensive tests | High |

---

## Estimated Effort

- **Schema changes**: 15 minutes
- **Core detection functions**: 30 minutes
- **Integration**: 30 minutes
- **Testing**: 45 minutes
- **Validation & documentation**: 30 minutes

**Total**: ~2.5 hours

---

## Documentation Updates

After implementation, update:
- `docs/FILENAME_CATEGORIZATION_GUIDE.md`: Add VCF variant type section
- `IMPLEMENTATION_SUMMARY.md`: Add entry for variant type detection
- Update MEMORY.md with patterns learned

---

**Plan Status**: Ready for implementation
**Approval Required**: Yes
**Implementation Order**: Sequential (Phase 1 → Phase 5)
