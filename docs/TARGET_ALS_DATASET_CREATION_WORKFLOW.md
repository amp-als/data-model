# Target ALS Dataset Creation Workflow

This guide documents the complete workflow for creating a Target ALS dataset in Synapse using the mapping-based annotation system.

## Overview

The Target ALS dataset creation uses a **two-step workflow** that separates metadata-to-annotation mapping from dataset creation. This allows you to leverage the mapping file to automatically populate file annotations from source metadata before creating the dataset entity.

## Prerequisites

1. **Synapse staging folder** containing Target ALS files (genomics, proteomics, etc.)
2. **Source metadata files** (CSV/XLSX) with subject and file-level metadata
3. **Mapping file** (`mapping/target_als_test.json`) - defines transformations from source columns to data model fields
4. **Data model schemas** - OmicFile, OmicDataset, etc.

## Complete Workflow

### Step 1: Generate Pre-Filled File Annotations

Use the `generate-file-templates` command to create file annotations populated from metadata:

```bash
python synapse_dataset_manager.py generate-file-templates \
  --folder syn12345678 \
  --type Omic \
  --mapping mapping/target_als_test.json \
  --metadata /path/to/target_als_metadata_folder/ \
  --output annotations/target_als_annotations.json \
  --skip-ai
```

**Parameters:**
- `--folder`: Synapse ID of staging folder with Target ALS files
- `--type`: File type - use `Omic` for genomics/proteomics data
- `--mapping`: Path to mapping dictionary file
- `--metadata`: Path to metadata folder (auto-discovers CSV/XLSX files) or individual files
- `--output`: Output path for generated annotations JSON

**What This Does:**
1. Connects to Synapse and enumerates all files in the staging folder
2. Loads the mapping file and all metadata files
3. For each file:
   - Creates empty annotation template from OmicFile schema
   - Matches file to subject using folder path structure (e.g., `/subject_123/sample.bam` → subject_123)
   - Fills template from metadata row using mapping transformations
   - Only fills fields that exist in OmicFile schema
4. Outputs JSON file with annotations for each file

**Output File Structure:**
```json
{
  "syn12345": {
    "subject001.bam": {
      "disease": "ALS",
      "diseaseSubtype": ["Probable_ALS", "limb_onset", "C9-ALS"],
      "biospecimenType": ["blood"],
      "platform": "Illumina NovaSeq 6000",
      "libraryLayout": ["single"],
      "fileFormat": "bam",
      "collection": ["Target ALS"],
      "_file_type": "OmicFile"
    }
  },
  "syn12346": {
    "subject002.bam": { ... }
  }
}
```

### Step 2: Generate Dataset-Level Annotations

Create an empty template for dataset-level metadata:

```bash
python synapse_dataset_manager.py generate-template \
  --type Omic \
  --output annotations/target_als_dataset_annotations.json
```

**Output:** `annotations/target_als_dataset_annotations.json`

### Step 3: Edit Annotations (Optional but Recommended)

Review and manually edit both annotation files:

**File annotations** (`target_als_annotations.json`):
- Verify mapped values are correct
- Add any missing file-level metadata
- Check that multi-valued fields (diseaseSubtype, biospecimenType) are properly formatted

**Dataset annotations** (`target_als_dataset_annotations.json`):
- Add dataset title, description
- Set dataset-level metadata (publication, contributors, etc.)
- Verify dataset type is correct

### Step 4: Create Dataset from Annotations

```bash
python synapse_dataset_manager.py create \
  --from-annotations \
  --project-id syn11111111 \
  --staging-folder syn12345678 \
  --dataset-name "target_als" \
  --execute
```

**Important:** The `--dataset-name` must match your annotation file prefixes:
- File annotations: `<dataset_name>_annotations.json`
- Dataset annotations: `<dataset_name>_dataset_annotations.json`

**What This Does:**
1. Validates file and dataset annotations against schemas
2. Creates dataset folder entity in your Synapse project
3. Applies annotations to all files in staging folder
4. Returns dataset Synapse ID

**Additional Options:**
```bash
# Add wiki documentation
--generate-wiki

# Create entity view for querying
--create-entity-view

# Create dataset snapshot/version
--create-snapshot --version-label "v1.0" --version-comment "Initial release"

# Move files to release folder
--release-folder syn99999999
```

## Important Schema Limitations

### What Fields Are Mappable to OmicFile?

The mapping system only fills fields that exist in the **OmicFile schema** (which inherits from BaseFile and OmicFileMixin).

**✅ Fields That WILL Work** (exist in OmicFile):
- `disease` - Disease diagnosis (BaseFile)
- `diseaseSubtype` - Multi-valued disease subtypes (BaseFile)
- `originalSubjectId` - Subject identifier (OmicFileMixin)
- `originalSampleId` - Sample identifier (OmicFileMixin)
- `biospecimenType` - Tissue/sample types (OmicFileMixin)
- `platform` - Sequencing platform (OmicFile)
- `libraryLayout` - Single/paired-end (OmicFileMixin)
- `libraryPreparationMethod` - Library prep kit (OmicFileMixin)
- `fileFormat` - File format (OmicFile)
- `collection` - Dataset collection (BaseFile)
- `url` - External URL (BaseFile)
- `contributor` - Contributors (BaseFile)

**❌ Fields That Will Be IGNORED** (not in OmicFile schema):
- `age`, `sex`, `race`, `ethnicity` - Subject demographics
- `country`, `heightCm`, `weightKg` - Additional demographics
- `yearOfSymptomOnset`, `yearOfDiagnosis` - Disease timeline
- `propAfricanGeneticAncestry`, `propEuropeanGeneticAncestry`, etc. - Genetic ancestry proportions

These Subject-level fields are mapped in `target_als_test.json` but will be silently skipped during annotation generation because they don't exist in the OmicFile schema.

### Future Options for Subject Demographics

To include subject demographics in file annotations, you would need to:

**Option 1: Extend OmicFile Schema** (denormalization)
- Add demographic fields to `modules/base/BaseFile.yaml` or `modules/datasets/OmicFile.yaml`
- Regenerate JSON schemas
- Allows filtering files by subject characteristics (e.g., "male subjects age 50-60")

**Option 2: Create Separate Subject Entities** (normalization)
- Import subject metadata as separate Subject entity tables
- Link files to subjects via `originalSubjectId`
- Requires joins for queries but avoids data duplication

**Current Recommendation:** Table subject demographics for future implementation (see `TARGET_ALS_UNMAPPABLE_FIELDS.md`).

## Mapping File Structure

The mapping file (`mapping/target_als_test.json`) defines transformations from source metadata columns to data model fields.

### Simple Mappings (Direct Field)
```json
"sample_id": "originalSampleId",
"gs_uri": "url"
```

### Value-Mapped Fields (Enum Transformations)
```json
"sex_reported": {
  "target": "sex",
  "values": {
    "Male": "Male",
    "Female": "Female"
  }
}
```

### Multi-Valued Mappings (Arrays)
```json
"site_of_motor_onset": {
  "target": "diseaseSubtype",
  "values": {
    "Bulbar": "bulbar_onset",
    "Limb": "limb_onset",
    "Bulbar | Limb": ["bulbar_onset", "limb_onset"]
  }
}
```

### Fixed Values (Constants)
```json
"collection": {
  "target": "collection",
  "value": "Target ALS"
}
```

### Empty Values (Unmappable)
```json
"age_in_years": {
  "target": "age",
  "values": {
    "-9999": "",  // Missing data code - excluded
    "20": "",     // Excluded because 'age' not in OmicFile schema
    ...
  }
}
```

## File-to-Subject Matching

The system matches files to metadata rows using the **folder path structure**:

```
Synapse Folder Structure:
/staging_folder/
  ├── subject_001/
  │   ├── sample.bam
  │   └── sample.bam.bai
  ├── subject_002/
  │   └── sample.cram
  └── subject_003/
      └── sample.vcf.gz

Metadata CSV:
subject_id,age,sex,disease,...
subject_001,45,Male,ALS,...
subject_002,52,Female,ALS,...
subject_003,60,Male,Control,...
```

The system extracts `subject_001` from the file path and looks it up in the metadata using the join column (determined by finding which mapping entry has `target: "originalSubjectId"`).

## Validation

After generating annotations, the `create --from-annotations` command validates:

1. **Schema Compliance**: All fields match the OmicFile JSON schema
2. **Enum Values**: Enum fields contain only allowed values
3. **Required Fields**: Required fields are present (though most are optional)
4. **Data Types**: Values match expected types (string, array, integer, etc.)

Validation errors will prevent dataset creation and must be fixed in the annotation JSON files.

## Troubleshooting

### Problem: Metadata rows not matching files

**Symptom:** Warning messages like `"No metadata match for subject_id 'subject_123'"`

**Solutions:**
1. Check folder path structure - subject IDs must be extractable from paths
2. Verify metadata CSV has correct `subject_id` column
3. Check for whitespace or formatting issues in IDs
4. Ensure mapping file has `originalSubjectId` target defined

### Problem: Mapped fields not appearing in annotations

**Symptom:** Fields in mapping file don't show up in output JSON

**Cause:** Fields don't exist in OmicFile schema - they're silently skipped

**Solutions:**
1. Check `TARGET_ALS_UNMAPPABLE_FIELDS.md` for list of unsupported fields
2. Remove unmappable fields from mapping OR
3. Extend OmicFile schema to include needed fields

### Problem: Enum validation errors

**Symptom:** `"Value 'X' not in allowed values for field 'Y'"`

**Solutions:**
1. Check that mapping values match enum definitions in `common-enums.yaml`
2. Update enum definitions if needed
3. Fix typos in mapping transformations (e.g., `Probable_ALS` vs `Probable ALS`)

### Problem: Multi-valued fields not merging correctly

**Symptom:** Subject has multiple disease subtypes but only one appears

**Current Limitation:** The current mapping system may not merge multiple `diseaseSubtype` values from different source columns correctly.

**Workaround:** Manually edit annotation JSON to combine values into arrays.

## Complete Example

```bash
# Step 1: Generate file annotations with mapping
python synapse_dataset_manager.py generate-file-templates \
  --folder syn52948473 \
  --type Omic \
  --mapping mapping/target_als_test.json \
  --metadata /data/target_als/metadata/ \
  --output annotations/target_als_wgs_annotations.json

# Output:
#   Loaded 150 subjects from 3 metadata file(s)
#   Metadata-filled: 148 / 150 files matched a metadata row

# Step 2: Generate dataset template
python synapse_dataset_manager.py generate-template \
  --type Omic \
  --output annotations/target_als_wgs_dataset_annotations.json

# Step 3: Edit annotations (manual)
# Edit both JSON files to add descriptions, verify values, etc.

# Step 4: Create dataset
python synapse_dataset_manager.py create \
  --from-annotations \
  --project-id syn12345678 \
  --staging-folder syn52948473 \
  --dataset-name "target_als_wgs" \
  --generate-wiki \
  --create-entity-view \
  --execute

# Output:
#   ✓ All file annotations valid
#   ✓ Dataset annotations valid
#   Created dataset: syn99999999
#   Applied annotations to 150 files
#   Created entity view: syn99999998
#   Generated wiki page
```

## Related Documentation

- **`TARGET_ALS_UNMAPPABLE_FIELDS.md`** - Fields that require new schemas (clinical assessments, biomarkers, etc.)
- **`mapping/target_als_test.json`** - Current mapping definitions
- **`modules/datasets/OmicFile.yaml`** - OmicFile schema definition
- **`modules/base/BaseFile.yaml`** - Base file attributes
- **`modules/shared/common-enums.yaml`** - Enum definitions

## Next Steps

1. **Run workflow on Target ALS staging data** to generate initial annotations
2. **Review and validate** generated annotations
3. **Create test dataset** with small subset of files
4. **Iterate on mapping** based on validation results
5. **Create production dataset** once mapping is validated
6. **Design new schemas** for unmappable fields (Phase 2)

---

**Document Version:** 1.0
**Last Updated:** 2026-03-11
**Author:** Data Model Implementation Team
