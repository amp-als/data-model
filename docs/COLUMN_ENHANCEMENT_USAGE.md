# Dataset Column Enhancement - Usage Guide

## Quick Reference

### New Functions Available

All new functions are in `synapse_dataset_manager.py`:

1. **`get_dataset_column_schema(dataset_type)`** - Get column definitions for a dataset type
2. **`get_column_order_template(dataset_type)`** - Get ordered column names
3. **`add_dataset_columns(syn, dataset_id, ..., dataset_type=None, ...)`** - Enhanced with type awareness
4. **`reorder_dataset_columns(syn, dataset_id, dataset_type=None, dry_run=True)`** - Reorder columns
5. **`verify_dataset_columns(syn, dataset_id, verbose=True)`** - Display column information
6. **`add_staging_folder_to_dataset(syn, dataset_id, staging_folder_id, dry_run=True)`** - Add entire folder

## Automatic Usage (CREATE Workflow)

When you run the CREATE workflow, the enhancements are **automatically applied**:

```bash
python synapse_dataset_manager.py create \
  --dataset-name "My Dataset" \
  --staging-folder syn12345678 \
  --from-annotations \
  --execute
```

### What Happens Automatically

1. **STEP 7: Add Dataset Columns**
   - Auto-detects dataset type (Clinical vs Omic)
   - Adds type-specific columns with size constraints
   - Shows: `[DRY_RUN]` or `✓ Added X columns`

2. **STEP 7b: Reorder Dataset Columns** ⭐ NEW
   - Automatically reorders columns for better UX
   - Puts important columns first (dataType, fileFormat, etc.)
   - Shows: `[DRY_RUN]` or `✓ Reordered X columns`

3. **STEP 7c: Verify Dataset Columns** ⭐ NEW (when VERBOSE=True)
   - Displays column summary
   - Shows faceted vs non-faceted counts
   - Lists column details with size constraints

### Example Output (Dry Run)

```
============================================================
STEP 7: ADDING DATASET COLUMNS
============================================================
  📊 Auto-detected dataset type: ClinicalDataset
  [DRY_RUN] Would add 13 columns to dataset (ClinicalDataset)
  [DRY_RUN] Columns: dataType, fileFormat, species, disease, studyType, dataFormat, studyPhase, keyMeasures, assessmentType, clinicalDomain, hasLongitudinalData, studyDesign, primaryOutcome

============================================================
STEP 7b: REORDERING DATASET COLUMNS
============================================================
  [DRY_RUN] Would reorder 13 columns
  [DRY_RUN] New order: id, name, dataType, fileFormat, studyType, species, disease, dataFormat, studyPhase, assessmentType...

============================================================
STEP 7c: VERIFYING DATASET COLUMNS
============================================================
  📊 Total columns: 13
  🔍 Faceted (searchable): 12
  📝 Non-faceted: 1

  Faceted columns:
   • dataType: STRING (max: 100) [enumeration]
   • fileFormat: STRING (max: 50) [enumeration]
   • species: STRING (max: 100) [enumeration]
   • disease: STRING (max: 100) [enumeration]
   • studyType: STRING (max: 100) [enumeration]
   ... and 7 more faceted columns
```

## Column Schemas by Dataset Type

### Clinical Dataset Columns

**Shared columns (6):**
- dataType, fileFormat, species, disease, studyType, dataFormat

**Clinical-specific (7):**
- studyPhase, keyMeasures, assessmentType, clinicalDomain
- hasLongitudinalData, studyDesign, primaryOutcome

**Total: 13 columns**

### Omic Dataset Columns

**Shared columns (6):**
- dataType, fileFormat, species, disease, studyType, dataFormat

**Omic-specific (7):**
- assay, platform, libraryStrategy, libraryLayout
- cellType, biospecimenType, processingLevel

**Total: 13 columns**

## Size Constraints (64KB Row Limit Prevention)

All columns have size constraints to prevent hitting Synapse's 64KB row limit:

- **STRING columns:** 50-250 characters max
- **STRING_LIST columns:** 10-20 items max
- **BOOLEAN columns:** no limit needed

### Example Constraints

```python
"dataType": max_size=100
"fileFormat": max_size=50
"disease": max_size=100
"studyDesign": max_size=150
"primaryOutcome": max_size=250

"dataFormat": max_list_len=10
"keyMeasures": max_list_len=20
"assessmentType": max_list_len=15
"assay": max_list_len=10
```

## Column Ordering

Columns are automatically ordered for better UX:

1. **System columns** (always first)
   - id, name

2. **High-priority annotations**
   - dataType, fileFormat, studyType, species, disease, dataFormat

3. **Type-specific columns**
   - Clinical: studyPhase, assessmentType, clinicalDomain, ...
   - Omic: assay, platform, libraryStrategy, ...

4. **Synapse metadata** (always last)
   - description, createdOn, createdBy, etag, modifiedOn, ...

## Manual Usage (Advanced)

### Using Functions Programmatically

```python
from synapseclient import Synapse
from synapse_dataset_manager import (
    get_dataset_column_schema,
    add_dataset_columns,
    reorder_dataset_columns,
    verify_dataset_columns
)

syn = Synapse()
syn.login()

dataset_id = "syn12345678"

# Add columns to existing dataset
add_dataset_columns(
    syn, dataset_id, all_schemas={},
    dataset_type='ClinicalDataset',
    dry_run=False
)

# Reorder columns
reorder_dataset_columns(
    syn, dataset_id,
    dataset_type='ClinicalDataset',
    dry_run=False
)

# Verify columns
verify_dataset_columns(syn, dataset_id, verbose=True)
```

### Getting Column Schema

```python
from synapse_dataset_manager import get_dataset_column_schema

# Get clinical columns
clinical_cols = get_dataset_column_schema('ClinicalDataset')

# Get omic columns
omic_cols = get_dataset_column_schema('OmicDataset')

# Each column is a dict with:
# {
#   "name": "dataType",
#   "type": ColumnType.STRING,
#   "facet": FacetType.ENUMERATION,
#   "max_size": 100,
#   "desc": "Data type"
# }
```

## Troubleshooting

### Issue: "Column already exists"

**Symptom:**
```
ℹ️  Column dataType already exists, skipping
```

**Solution:** This is expected behavior. The function checks for existing columns and only adds new ones.

### Issue: "Dataset has no columns"

**Symptom:**
```
ℹ️  Dataset has no columns
```

**Solution:** Run `add_dataset_columns()` first before `verify_dataset_columns()`.

### Issue: Size constraint violations

**Symptom:** Synapse API error about row size limit

**Solution:** The implementation already includes size constraints. If you still hit this, you may need to:
1. Reduce `max_size` values in `get_dataset_column_schema()`
2. Reduce `max_list_len` values for STRING_LIST columns
3. Remove non-essential columns

### Issue: Wrong dataset type detected

**Symptom:** Omic dataset gets clinical columns or vice versa

**Solution:** Explicitly set `_dataset_type` in your dataset annotations:
```json
{
  "_dataset_type": "OmicDataset",
  ...
}
```

Or pass `dataset_type` parameter to functions:
```python
add_dataset_columns(syn, dataset_id, all_schemas,
                   dataset_type='OmicDataset',
                   dry_run=False)
```

## Configuration

### Controlling Column Addition

The column addition happens automatically in the CREATE workflow. To disable:

1. Skip STEP 7 by making the dataset a link dataset:
   ```bash
   python synapse_dataset_manager.py create --link-dataset ...
   ```

### Controlling Verbosity

STEP 7c (verification) only runs when `VERBOSE=True`:

```bash
# In config.yaml
workflow:
  verbose: true

# Or via environment variable
export VERBOSE=true
```

### Controlling Dry Run

All steps respect the dry-run flag:

```bash
# Dry run (default)
python synapse_dataset_manager.py create ... --dry-run

# Execute
python synapse_dataset_manager.py create ... --execute
```

## Best Practices

1. **Always run with `--dry-run` first** to see what will happen
2. **Use `--execute` only after reviewing** the dry-run output
3. **Enable verbose mode** (`VERBOSE=true`) for debugging
4. **Set `_dataset_type` in annotations** for explicit type control
5. **Verify columns in Synapse UI** after creation

## Future Enhancements (Optional)

These are NOT implemented yet but could be added:

1. CLI commands for column management:
   ```bash
   python synapse_dataset_manager.py add-columns syn12345 --type Clinical
   python synapse_dataset_manager.py reorder-columns syn12345
   python synapse_dataset_manager.py verify-columns syn12345
   ```

2. Custom column schemas in `config.yaml`:
   ```yaml
   column_schemas:
     ClinicalDataset:
       - name: customField
         type: STRING
         facet: ENUMERATION
         max_size: 100
   ```

3. Dynamic enum values from actual data
4. Column schema validation before creation

## Support

- Implementation details: `DATASET_COLUMN_ENHANCEMENT_IMPLEMENTATION.md`
- Original plan: Check plan mode transcript
- Reference notebook: `notebooks/trehalose_biomarker_annotations.ipynb`
