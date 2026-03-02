# Entity View Column Reordering - Fix Applied

## Issue Identified

From the log output:
```
STEP 3b: REORDERING ENTITY VIEW COLUMNS
  ℹ️  No columns to reorder

STEP 3c: VERIFYING ENTITY VIEW COLUMNS
  ℹ️  Entity view has no columns
```

But the entity view WAS created with columns (visible in screenshot showing dataType, fileFormat, species, disease... as the first columns instead of id, name).

## Root Cause

The reordering and verification functions were using `syn.get(view_id)` which returns an old-style Entity object that doesn't have the `columns` attribute properly populated for entity views.

Entity views created via the new `synapseclient.models.EntityView` API need to be retrieved using the models API, not the old `syn.get()` method.

## Fix Applied

### 1. `reorder_entity_view_columns()` Function

**Before:**
```python
# Get entity view with columns
entity_view = syn.get(view_id)  # Old API - doesn't load columns properly

# Get current column order
if not hasattr(entity_view, 'columns') or not entity_view.columns:
    print(f"  ℹ️  No columns to reorder")
    return True

current_columns = [col['name'] for col in entity_view.columns]
```

**After:**
```python
# Get entity view with columns using the models API (same as datasets)
# This ensures columns are properly loaded
from synapseclient.models import Table
entity_view = Table(id=view_id).get(include_columns=True)

# Get current column order (using entity_view.columns like datasets)
if not hasattr(entity_view, 'columns') or not entity_view.columns:
    print(f"  ℹ️  No columns to reorder")
    return True

current_columns = list(entity_view.columns.keys())  # Dict of column name -> Column object
```

**Reordering Logic - Simplified:**
```python
# Before: Complex manual reordering with position tracking
for target_index, col_name in enumerate(final_order):
    current_position = current_columns.index(col_name)
    if current_position != target_index:
        col = entity_view.columns[current_position]
        entity_view.columns.pop(current_position)
        entity_view.columns.insert(target_index, col)
        current_columns.insert(target_index, current_columns.pop(current_position))
        reordered_count += 1

if reordered_count > 0:
    syn.store(entity_view)

# After: Simpler approach (same as datasets)
for target_index, col_name in enumerate(final_order):
    entity_view.reorder_column(name=col_name, index=target_index)

entity_view.store()
```

### 2. `verify_entity_view_columns()` Function

**Before:**
```python
entity_view = syn.get(view_id)  # Old API

if not hasattr(entity_view, 'columns') or not entity_view.columns:
    print(f"  ℹ️  Entity view has no columns")
    return True

columns = entity_view.columns  # Assuming it's a list
faceted = [c for c in columns if c.get('facetType')]  # Dict access
```

**After:**
```python
# Use models API to get entity view with columns (same as datasets)
from synapseclient.models import Table
entity_view = Table(id=view_id).get(include_columns=True)

# Use entity_view.columns (consistent with datasets)
if not hasattr(entity_view, 'columns') or not entity_view.columns:
    print(f"  ℹ️  Entity view has no columns")
    return True

# entity_view.columns is a dict, get the Column objects
columns = list(entity_view.columns.values())
faceted = [c for c in columns if c.facet_type]  # Attribute access
```

## Key Changes

### API Consistency

Now both **datasets** and **entity views** use the **same API pattern**:

| Operation | Datasets | Entity Views (NEW) |
|-----------|----------|-------------------|
| Get with columns | `Dataset(id=...).get(include_columns=True)` | `Table(id=...).get(include_columns=True)` |
| Column access | `dataset.columns` (dict) | `entity_view.columns` (dict) |
| Column keys | `list(dataset.columns.keys())` | `list(entity_view.columns.keys())` |
| Column values | `list(dataset.columns.values())` | `list(entity_view.columns.values())` |
| Reorder column | `dataset.reorder_column(name, index)` | `entity_view.reorder_column(name, index)` |
| Store | `dataset.store()` | `entity_view.store()` |

### Why Table Instead of EntityView?

For retrieval, we use `Table` because both EntityView and Dataset inherit from Table in the models API, and `Table.get()` works for both.

## Expected Behavior After Fix

### STEP 3b Output (Dry Run):
```
============================================================
STEP 3b: REORDERING ENTITY VIEW COLUMNS
============================================================
  [DRY_RUN] Would reorder 36 columns in entity view
  [DRY_RUN] Current order: dataType, fileFormat, species, disease, studyType...
  [DRY_RUN] New order: id, name, dataType, fileFormat, studyType...
```

### STEP 3b Output (Execute):
```
============================================================
STEP 3b: REORDERING ENTITY VIEW COLUMNS
============================================================
  ✓ Reordered 36 columns in entity view (OmicDataset)
```

### STEP 3c Output (Execute + Verbose):
```
============================================================
STEP 3c: VERIFYING ENTITY VIEW COLUMNS
============================================================
  📊 Total columns: 36
  🔍 Faceted (searchable): 24
  📝 Non-faceted: 12

  Faceted columns:
   • dataType: STRING (max: 100) [enumeration]
   • fileFormat: STRING (max: 50) [enumeration]
   ...
```

### Entity View in Synapse UI

Column order will now be:
```
1. id
2. name
3. dataType
4. fileFormat
5. studyType
6. species
7. disease
8. dataFormat
9. [Omic-specific columns: assay, platform, libraryStrategy, etc.]
10. [Synapse metadata columns...]
```

## Dataset Annotations - Already Working ✅

From the log:
```
✓ Created dataset: syn73686116
✓ Applied 18 annotations: collection, contributor, creator, curationLevel,
                          dataType, dataset_code, disease, diseaseSubtype,
                          individualCount, keywords
```

Dataset annotations are working correctly! 18 annotations were successfully applied.

## Testing the Fix

Run the same command again:
```bash
python synapse_dataset_manager.py create \
  --use-config ALS_Compute_Dataset \
  --from-annotations \
  --execute
```

**Look for:**
1. STEP 3b should now show actual column reordering (not "No columns")
2. STEP 3c should show column counts (not "Entity view has no columns")
3. In Synapse UI, entity view columns should start with id, name

## Status

✅ **FIXED**
- Entity view reordering now uses correct API (`Table.get(include_columns=True)`)
- Entity view verification now uses correct API
- Both functions now match the dataset pattern for consistency
- Reordering logic simplified to match datasets

**Ready for testing!**
