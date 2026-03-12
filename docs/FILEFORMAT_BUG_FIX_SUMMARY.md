# fileFormat Bug Fix Summary

## Bug Description

PDF and TXT files were getting incorrect `fileFormat` values in the generated annotations. For example:
- `NEUBJ004MUV.gc_bias.pdf` → `fileFormat: "tbi"` ❌ (should be `"pdf"`)
- Other PDF/TXT files were getting formats like `"crai"`, `"bai"`, `"md5"` instead of correct values

**Impact**: 351 files affected (40 PDF files + 311 TXT files) in the Target ALS annotations

## Root Cause

The bug was in `synapse_dataset_manager.py` function `enrich_metadata_with_file_info()` (lines 1091-1103).

**Problem**: The function prioritized metadata columns over the explicit `file_name` parameter:

```python
# OLD CODE (BUGGY)
for col in ['gs_uri', 'url', 'file_name', 'filename', 'name']:
    if col in enriched and enriched[col]:
        file_identifier = enriched[col]  # ❌ Uses metadata first!
        break

if not file_identifier and file_name:
    file_identifier = file_name  # Only used as fallback
```

**Why this caused the bug**:
1. Metadata loading in `load_all_metadata_files()` uses `.update()` to merge rows (lines 775-791)
2. When a subject has multiple files, only the LAST file's `gs_uri` is retained
3. When enriching a PDF file, it used the metadata's stale `gs_uri` (pointing to a `.tbi` file)
4. Result: PDF gets `fileFormat: "TBI"` instead of `"PDF"`

## Solution

**Fixed the priority order** in `enrich_metadata_with_file_info()` to prioritize the explicit `file_name` parameter:

```python
# NEW CODE (FIXED)
# First: Use explicit file_name parameter if provided
if file_name:
    file_identifier = file_name
# Second: Fall back to metadata columns
else:
    for col in ['gs_uri', 'url', 'file_name', 'filename', 'name']:
        if col in enriched and enriched[col]:
            file_identifier = enriched[col]
            break
```

**Rationale**:
- The `file_name` parameter comes directly from Synapse file listing (ground truth)
- Metadata columns may be stale/polluted from `.update()` merging
- Explicit parameters should take precedence over inherited data

## Changes Made

### 1. Fixed Priority Order
**File**: `synapse_dataset_manager.py`
**Lines**: 1091-1106

Changed the order to check `file_name` parameter FIRST, then fall back to metadata columns.

### 2. Updated Docstring
**File**: `synapse_dataset_manager.py`
**Lines**: 1082-1088

Updated the docstring to document the new priority behavior and explain why it's important.

### 3. Added Regression Test
**File**: `test_file_categorization.py`
**Lines**: 246-268

Added `test_file_name_parameter_priority()` test that reproduces the exact bug scenario and verifies the fix.

## Verification

### Unit Tests
```bash
$ python -m pytest test_file_categorization.py -v
```
**Result**: ✅ All 43 tests pass (42 existing + 1 new)

### Integration Tests
```bash
$ python verify_fileformat_fix.py
```
**Results**:
- ✅ PDF with polluted metadata → correctly gets `fileFormat: "PDF"`
- ✅ TXT with polluted metadata → correctly gets `fileFormat: "TXT"`
- ✅ Backward compatibility → gs_uri fallback still works when no filename provided

### Bug Impact Analysis
```bash
$ python check_old_annotations.py
```
**Results**:
- 40 PDF files had wrong fileFormat (e.g., `"tbi"`, `"crai"`)
- 311 TXT files had wrong fileFormat (e.g., `"tbi"`, `"md5"`)
- Total: 351 files affected

## Test Results

### Before Fix (Old Annotations)
```
NEUBJ004MUV.gc_bias.pdf
  fileFormat: tbi ❌
```

### After Fix (New Behavior)
```
NEUBJ004MUV.gc_bias.pdf
  _file_extension: pdf ✅
  _computed_fileFormat: PDF ✅
  _file_category: gc_bias_plot ✅
```

## Edge Cases Verified

- ✅ Files with no metadata: Still work (filename parameter is used)
- ✅ Files with correct metadata: Still work (filename parameter preferred)
- ✅ Files with polluted metadata: NOW FIXED (filename parameter takes priority)
- ✅ Files with multiple dots: Still correctly extract extension (e.g., `.txt.gz`)
- ✅ Compressed files (.txt.gz): Still correctly identified as TXT
- ✅ Index files (.tbi, .bai): Still correctly identified
- ✅ Backward compatibility: gs_uri fallback works when no filename provided

## Files Changed

| File | Changes | Lines |
|------|---------|-------|
| `synapse_dataset_manager.py` | Fixed priority order in `enrich_metadata_with_file_info()` | 1091-1106 |
| `synapse_dataset_manager.py` | Updated function docstring | 1082-1088 |
| `test_file_categorization.py` | Added regression test | 246-268 |

## Additional Files Created

| File | Purpose |
|------|---------|
| `verify_fileformat_fix.py` | Integration test script demonstrating the fix |
| `check_old_annotations.py` | Script to analyze bug impact on old annotations |
| `FILEFORMAT_BUG_FIX_SUMMARY.md` | This document |

## Next Steps

To regenerate corrected annotations for Target ALS data:

```bash
# Regenerate file annotations with the fix
python synapse_dataset_manager.py generate-file-templates \
  --folder syn73810834 \
  --type Omic \
  --mapping mapping/target_als_test.json \
  --metadata downloads/Target_ALS/metadata/ \
  --output annotations/target_als_corrected_annotations.json
```

The regenerated annotations will have correct `fileFormat` values for all 351 previously affected files.

## Success Criteria

✅ **Bug Fixed**: PDF files now get `fileFormat: "PDF"`, not `"TBI"`
✅ **No Regression**: All existing tests continue to pass
✅ **New Test Added**: Regression test prevents the bug from returning
✅ **Minimal Risk**: Surgical fix with clear scope and minimal side effects
✅ **Documentation**: Bug cause, fix, and verification documented

---

**Implementation Date**: 2026-03-11
**Developer**: Claude Sonnet 4.5
**Status**: ✅ Complete
