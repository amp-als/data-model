# Debugging Fixes - Column Ordering & Dataset Annotations

## Issues Fixed

### Issue 1: Entity View Column Ordering (id, name not first)

**Problem:** The id and name columns were not appearing as the first two columns in entity views.

**Root Cause:** Entity view reordering was using the dataset column order template, which is correct, but the actual reordering logic might not have been working properly.

**Fix Applied:**
1. Created `get_entity_view_column_order_template()` function that reuses the dataset template (id, name first)
2. Updated `reorder_entity_view_columns()` to use this new function
3. Added debugging output to show current vs new column order

**Expected Column Order:**
```
1. id
2. name
3. dataType
4. fileFormat
5. studyType
6. species
7. disease
8. dataFormat
9. [Clinical or Omic specific columns...]
10. [Synapse metadata columns...]
```

### Issue 2: Dataset Entity Not Receiving Annotations

**Problem:** Dataset entity appears to not be receiving annotations.

**Investigation:**
The code DOES apply annotations at line 870:
```python
dataset = Dataset(
    name=dataset_name,
    parent_id=project_id,
    annotations=cleaned  # <-- Annotations ARE applied here
)
```

**Potential Causes:**

1. **Metadata fields filtered out** - Fields starting with `_` (like `_dataset_type`) are intentionally removed by `clean_annotations_for_synapse()` as they're internal metadata, not user-visible annotations.

2. **File-level fields removed** - The following fields are intentionally removed from dataset annotations (lines 831-835):
   ```python
   file_level_fields = {
       'assay', 'platform', 'specimenType', 'cellType', 'libraryLayout',
       'FACSPopulation', 'GEOSuperSeries', 'biospecimenType', 'originalSampleName',
       'fileFormat', 'sex', 'age', 'diagnosis', 'tissueType', 'tissueOrigin'
   }
   ```
   These belong on files, not the dataset entity.

3. **Empty values filtered** - Empty strings, empty arrays, and None values are removed.

**Fix Applied:**
Added debugging output to show:
- How many annotations are being applied
- What the annotation keys are (first 10)
- Warning if no annotations are applied

**What Annotations SHOULD Be On Dataset:**
Dataset-level annotations (not file-level):
- `name` - Dataset name
- `description` - Dataset description
- `studyType` - Type of study
- `disease` - Disease being studied
- `species` - Species
- `dataType` - Overall data type
- `url` - For link datasets
- etc.

**What Annotations Should NOT Be On Dataset:**
File-level annotations (these go on individual files):
- `assay`, `platform`, `fileFormat`
- `sex`, `age`, `diagnosis`
- `cellType`, `biospecimenType`
- etc.

---

## Debugging Output Added

### For Entity View Column Reordering

When running with dry-run or execute, you'll now see:
```
============================================================
STEP 3b: REORDERING ENTITY VIEW COLUMNS
============================================================
  [DRY_RUN] Would reorder 13 columns in entity view
  [DRY_RUN] Current order: name, dataType, fileFormat, id, studyType...
  [DRY_RUN] New order: id, name, dataType, fileFormat, studyType...
```

Or when executing:
```
  ✓ Reordered 13 columns in entity view (ClinicalDataset)
```

### For Dataset Annotations

When creating a dataset, you'll now see:
```
============================================================
STEP 5: CREATING DATASET ENTITY
============================================================
  [DRY_RUN] Would create dataset 'My Dataset' with 5 annotations
  [DRY_RUN] Annotations: name, description, studyType, disease, species
```

Or when executing:
```
  ✓ Created dataset: syn12345678
  ✓ Applied 5 annotations: name, description, studyType, disease, species
```

Or if no annotations:
```
  ✓ Created dataset: syn12345678
  ⚠️  Warning: No annotations were applied to dataset
```

---

## How to Debug

### If Entity View Columns Are Still Out of Order

1. **Check dry-run output:**
   ```bash
   python synapse_dataset_manager.py create \
     --dataset-name "Test" \
     --staging-folder syn12345 \
     --from-annotations \
     --dry-run
   ```

2. **Look for STEP 3b output:**
   ```
   STEP 3b: REORDERING ENTITY VIEW COLUMNS
     [DRY_RUN] Current order: [shows actual order]
     [DRY_RUN] New order: [shows desired order]
   ```

3. **Verify the template:**
   ```python
   from synapse_dataset_manager import get_entity_view_column_order_template

   order = get_entity_view_column_order_template('ClinicalDataset')
   print(f"First 5 columns: {order[:5]}")
   # Should show: ['id', 'name', 'dataType', 'fileFormat', 'studyType']
   ```

4. **Check if reordering is actually running:**
   - Make sure STEP 3b is not being skipped
   - Check for error messages in the output

### If Dataset Annotations Are Missing

1. **Check the dataset annotation file:**
   ```bash
   cat annotations/MyDataset_dataset_annotations.json
   ```

   Should contain dataset-level fields like:
   ```json
   {
     "name": "My Dataset",
     "description": "Dataset description",
     "studyType": "Observational",
     "disease": "ALS",
     "_dataset_type": "ClinicalDataset"
   }
   ```

2. **Check dry-run output for STEP 5:**
   ```
   STEP 5: CREATING DATASET ENTITY
     [DRY_RUN] Would create dataset 'My Dataset' with 4 annotations
     [DRY_RUN] Annotations: name, description, studyType, disease
   ```

   Note: `_dataset_type` is NOT shown because it's metadata (filtered out).

3. **Common issues:**

   a. **Only metadata fields in annotation file:**
   ```json
   {
     "_dataset_type": "ClinicalDataset"
   }
   ```
   After cleaning, this results in 0 annotations (underscore fields removed).

   **Solution:** Add dataset-level fields to the annotation file.

   b. **File-level fields in dataset annotations:**
   ```json
   {
     "assay": "RNA-seq",
     "fileFormat": "fastq",
     ...
   }
   ```
   These are filtered out (they belong on files, not dataset).

   **Solution:** Keep file-level annotations in the file annotation file, not dataset annotation file.

   c. **Empty values:**
   ```json
   {
     "name": "",
     "description": "",
     "studyType": []
   }
   ```
   Empty strings and empty arrays are filtered out.

   **Solution:** Provide actual values for annotations.

4. **Verify in Synapse UI:**
   - Navigate to the dataset in Synapse
   - Click on the dataset entity (not the files)
   - Check the "Annotations" tab
   - You should see dataset-level annotations there

---

## Testing the Fixes

### Test 1: Verify Entity View Column Order

```bash
python synapse_dataset_manager.py create \
  --dataset-name "Test Dataset" \
  --staging-folder syn12345678 \
  --from-annotations \
  --dry-run
```

**Expected Output:**
```
STEP 3b: REORDERING ENTITY VIEW COLUMNS
  [DRY_RUN] Current order: [whatever order it starts with]
  [DRY_RUN] New order: id, name, dataType, fileFormat, studyType, species...
```

**Verify:** New order starts with `id, name`.

### Test 2: Verify Dataset Annotations

```bash
python synapse_dataset_manager.py create \
  --dataset-name "Test Dataset" \
  --staging-folder syn12345678 \
  --from-annotations \
  --dry-run
```

**Expected Output:**
```
STEP 5: CREATING DATASET ENTITY
  [DRY_RUN] Would create dataset 'Test Dataset' with N annotations
  [DRY_RUN] Annotations: [list of annotation keys]
```

**Verify:**
- N > 0 (you have some annotations)
- The annotation list contains dataset-level fields (not file-level fields)
- No underscore-prefixed fields in the list (those are metadata)

### Test 3: Execute and Verify in Synapse

```bash
python synapse_dataset_manager.py create \
  --dataset-name "Test Dataset" \
  --staging-folder syn12345678 \
  --from-annotations \
  --execute
```

**Then in Synapse UI:**
1. Navigate to the entity view → verify columns start with id, name
2. Navigate to the dataset entity → check Annotations tab → verify annotations are there

---

## Files Modified

- `synapse_dataset_manager.py`:
  - Added `get_entity_view_column_order_template()` function
  - Updated `reorder_entity_view_columns()` to use new template
  - Added debugging output for dataset annotations
  - Added debugging output for column reordering (both entity views and datasets)

---

## Summary

✅ **Entity View Column Order:** Fixed to use correct template (id, name first)
✅ **Dataset Annotations:** Added debugging to show what's being applied
✅ **Debugging Output:** Enhanced to help diagnose issues

**Next Steps:**
1. Run with `--dry-run` to see the new debugging output
2. Check if entity view columns show correct order
3. Check if dataset annotations are being applied
4. If issues persist, use the debugging steps above to investigate
