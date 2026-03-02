# New Features Documentation - Synapse Dataset Manager

This document covers the new features added to `synapse_dataset_manager.py`:

1. **Link Datasets** - Create datasets that reference external URLs without files
2. **Generate Template Command** - Generate empty dataset annotation templates
3. **Add Link File Command** - Create file entities with external URL references

## Table of Contents
- [Setup and Testing](#setup-and-testing)
- [Feature 1: Link Datasets](#feature-1-link-datasets)
- [Feature 2: Generate Template Command](#feature-2-generate-template-command)
- [Feature 3: Add Link File Command](#feature-3-add-link-file-command)
- [Configuration Examples](#configuration-examples)
- [Code Snippets](#code-snippets)

---

## Setup and Testing

### Environment Activation

**IMPORTANT:** To test this code, you must activate the mamba environment:

```bash
mamba activate amp-als
```

### Verify Installation

```bash
python synapse_dataset_manager.py --help
```

---

## Feature 1: Link Datasets

Link datasets are datasets that reference external URLs (e.g., GEO, dbGaP) without containing any files locally in Synapse.

### Key Characteristics

- ✅ No files uploaded to Synapse
- ✅ Required `url` annotation field pointing to external data location
- ✅ Supports wiki generation
- ✅ Supports collections
- ❌ Does not support snapshots (requires files)
- ❌ Does not support entity views (no files to view)

### CLI Usage

#### Step 1: Generate Dataset Template

```bash
# Using CLI flag
python synapse_dataset_manager.py create \
  --dataset-name "External GEO Dataset" \
  --link-dataset

# Using config
python synapse_dataset_manager.py create --use-config MY_LINK_DATASET
```

This creates a dataset annotation template at:
```
annotations/External_GEO_Dataset_dataset_annotations.json
```

#### Step 2: Edit Annotations

Edit the generated JSON file and **add the required `url` field**:

```json
{
  "url": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE12345",
  "studyName": "Gene Expression in Disease X",
  "description": "External dataset hosted at GEO",
  "dataType": ["transcriptomics"],
  "_dataset_type": "OmicDataset"
}
```

#### Step 3: Create Dataset

```bash
# With CLI flag
python synapse_dataset_manager.py create \
  --dataset-name "External GEO Dataset" \
  --link-dataset \
  --from-annotations \
  --execute

# With config
python synapse_dataset_manager.py create \
  --use-config MY_LINK_DATASET \
  --from-annotations \
  --execute
```

### Config File Configuration

Add to `config.yaml`:

```yaml
datasets:
  MY_LINK_DATASET:
    # Required fields
    dataset_name: "External GEO Reference Dataset"
    dataset_type: "Omic"  # or "Clinical"

    # Enable link dataset mode
    link_dataset: true

    # Optional: Wiki generation
    generate_wiki: true

    # Optional: Add to collection
    add_to_collection: true
    collection_id: "syn72642710"

    # Optional: Contact information (for wiki)
    contact: "PI Name <pi@institution.edu>"
    institution: "Research Institution"
    contributors: "Contributor 1, Contributor 2"

    # Note: These are NOT supported for link datasets
    # staging_folder: "synXXXXX"  # Ignored - link datasets have no files
    # create_snapshot: true       # Not supported - requires files
```

### Validation

Link datasets MUST have a `url` field. The script will validate this during creation:

```
✓ Link dataset validation passed
  External URL: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE12345
```

If missing:
```
❌ Link dataset validation failed: Missing required 'url' field
💡 Link datasets must have a 'url' annotation pointing to the external dataset location
```

### Workflow Differences

Link datasets skip these steps:
- **Step 1:** File enumeration (skipped)
- **Step 2:** File annotation generation (skipped)
- **Phase 2:** All file operations (skipped)
- **Step 6:** Add files to dataset (skipped)
- **Step 7:** Dataset columns (skipped)
- **Step 10:** Snapshot creation (skipped - shows warning)
- **Step 12:** Release folder move (skipped)

Link datasets execute these steps normally:
- **Step 5:** Dataset creation ✅
- **Step 8:** Wiki generation (optional) ✅
- **Step 11:** Add to collection (optional) ✅

### Error Handling

**Conflicting Options:**
```bash
# This will fail:
python synapse_dataset_manager.py create \
  --link-dataset \
  --staging-folder syn12345  # ERROR!

# Error message:
❌ Error: --staging-folder cannot be used with --link-dataset
   Link datasets reference external URLs and do not contain files
```

---

## Feature 2: Generate Template Command

Generate empty dataset annotation templates without connecting to Synapse or requiring staging folders.

### Purpose

- Preview available annotation fields for different dataset types
- Create templates for manual annotation before dataset creation
- Useful for link datasets where you only need dataset metadata

### CLI Usage

```bash
# Generate Clinical dataset template
python synapse_dataset_manager.py generate-template --type Clinical

# Generate Omic dataset template
python synapse_dataset_manager.py generate-template --type Omic

# Generate generic Dataset template
python synapse_dataset_manager.py generate-template --type Dataset

# Specify custom output location
python synapse_dataset_manager.py generate-template \
  --type Clinical \
  --output my_templates/clinical_template.json
```

### Short Flags

```bash
python synapse_dataset_manager.py generate-template -t Omic -o omic.json
```

### Default Output Locations

Without `--output`, templates are saved to:
```
annotations/clinical_dataset_template.json   # --type Clinical
annotations/omic_dataset_template.json       # --type Omic
annotations/dataset_dataset_template.json    # --type Dataset
```

### Template Structure

Generated templates include:
- All fields from the JSON schema
- Empty default values based on field type
- Metadata fields (`_dataset_type`, `_schema_source`, `_created_timestamp`)
- Enum value hints in the schema

Example output:
```json
{
  "studyName": "",
  "studyType": "",
  "dataType": [""],
  "species": [""],
  "description": "",
  "url": "",
  "collection": [""],
  "_dataset_type": "ClinicalDataset",
  "_schema_source": "json-schema",
  "_created_timestamp": "2026-02-05T10:30:00"
}
```

### Use Cases

1. **Preview Schema Fields:**
   ```bash
   python synapse_dataset_manager.py generate-template --type Clinical
   cat annotations/clinical_dataset_template.json
   ```

2. **Create Template for Link Dataset:**
   ```bash
   python synapse_dataset_manager.py generate-template \
     --type Omic \
     --output link_dataset_template.json

   # Edit template, add URL
   # Then use in link dataset creation
   ```

3. **Compare Dataset Types:**
   ```bash
   python synapse_dataset_manager.py generate-template --type Clinical -o clinical.json
   python synapse_dataset_manager.py generate-template --type Omic -o omic.json
   diff clinical.json omic.json
   ```

---

## Feature 3: Add Link File Command

Create File entities that reference external URLs without uploading actual data to Synapse. These "link files" can be added to datasets alongside regular files.

### Purpose

- Reference external data sources (GEO datasets, dbGaP studies, supplementary data)
- Create mixed datasets with both local files and external references
- Add metadata/annotations to external resources within your dataset

### Key Characteristics

- Uses `File` entity with `external_url` and `synapse_store=False`
- No data uploaded to Synapse (only metadata)
- Can have annotations like regular files
- Can be added to datasets
- Appears in dataset file listings

### CLI Usage

#### Basic Usage

```bash
python synapse_dataset_manager.py add-link-file \
  --name "GEO Dataset GSE12345" \
  --url "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE12345" \
  --execute
```

#### Add to Dataset

```bash
python synapse_dataset_manager.py add-link-file \
  --name "External RNA-seq Data" \
  --url "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE12345" \
  --dataset-id syn67890123 \
  --execute
```

#### With Annotations

```bash
python synapse_dataset_manager.py add-link-file \
  --name "Supplementary Proteomics Data" \
  --url "https://example.com/supplementary_data.zip" \
  --dataset-id syn67890123 \
  --annotations '{"dataType": "proteomics", "fileFormat": "raw", "platform": "Olink"}' \
  --execute
```

#### Dry Run (Default)

```bash
# Preview what would be created (DRY_RUN=true by default)
python synapse_dataset_manager.py add-link-file \
  --name "Test Link" \
  --url "https://example.com/data.txt"

# Output:
[DRY_RUN] Would create link file 'Test Link'
  URL: https://example.com/data.txt
  Parent: syn68702804
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--name` | Yes | Name for the link file entity |
| `--url` | Yes | External URL to reference |
| `--dataset-id` | No | Dataset ID to add the link to (defaults to project) |
| `--annotations` | No | JSON string of annotations |
| `--execute` | No | Execute the operation (overrides dry-run) |
| `--dry-run` | No | Enable dry-run mode |

### Annotation Format

Annotations must be valid JSON:

```json
{
  "dataType": "transcriptomics",
  "fileFormat": "CEL",
  "platform": "Affymetrix",
  "assay": ["RNA-seq"],
  "description": "External microarray data from GEO"
}
```

### Use Cases

#### 1. Add External Reference to Existing Dataset

```bash
# Create dataset first (normal workflow)
python synapse_dataset_manager.py create \
  --staging-folder syn12345 \
  --dataset-name "My Mixed Dataset" \
  --from-annotations \
  --execute

# Add external reference
python synapse_dataset_manager.py add-link-file \
  --name "Related GEO Study" \
  --url "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE99999" \
  --dataset-id syn67890 \
  --annotations '{"dataType": "related_study"}' \
  --execute
```

#### 2. Create Dataset with Only External Links

```bash
# Create empty dataset
python synapse_dataset_manager.py create \
  --dataset-name "External References Collection" \
  --link-dataset \
  --from-annotations \
  --execute

# Add multiple external links
python synapse_dataset_manager.py add-link-file \
  --name "GEO Dataset 1" \
  --url "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE11111" \
  --dataset-id syn67890 \
  --execute

python synapse_dataset_manager.py add-link-file \
  --name "GEO Dataset 2" \
  --url "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE22222" \
  --dataset-id syn67890 \
  --execute
```

#### 3. Add Supplementary Materials

```bash
python synapse_dataset_manager.py add-link-file \
  --name "Supplementary Methods" \
  --url "https://journal.com/article/supplementary.pdf" \
  --dataset-id syn67890 \
  --annotations '{"fileFormat": "pdf", "dataType": "documentation"}' \
  --execute
```

### Implementation Details

The link file is created using:

```python
File(
    parent_id=parent_id,
    name=name,
    path=temp_file.name,        # Temporary placeholder (not uploaded)
    external_url=url,            # External URL reference
    synapse_store=False          # Prevents file upload
).store()
```

A temporary placeholder file is created locally but **not uploaded** to Synapse due to `synapse_store=False`. Only the metadata and external URL are stored.

---

## Configuration Examples

### Complete Link Dataset with External File References

```yaml
synapse:
  project_id: "syn68702804"
  datasets_collection_id: "syn72642710"

datasets:
  GEO_REFERENCE_DATASET:
    # Dataset configuration
    dataset_name: "GEO Multi-Study Reference"
    dataset_type: "Omic"
    link_dataset: true

    # Wiki configuration
    generate_wiki: true
    contact: "Dr. Jane Smith <jsmith@university.edu>"
    institution: "University Research Center"
    contributors: "Jane Smith, John Doe, Alice Johnson"

    # Collection
    add_to_collection: true
    collection_id: "syn72642710"
```

### Mixed Dataset (Local Files + External Links)

```yaml
datasets:
  MIXED_DATASET:
    # Has both local files and external references
    dataset_name: "Primary Data with External References"
    dataset_type: "Clinical"
    staging_folder: "syn12345678"

    # Normal dataset creation
    generate_wiki: true
    create_snapshot: true
    version_label: "v1.0"

    # External links added separately via add-link-file command
```

---

## Code Snippets

### Programmatic Usage (Python)

#### 1. Add File Entity to Dataset

```python
import synapseclient
from synapseclient import Dataset
from synapseclient.models import File

syn = synapseclient.Synapse()
syn.login()

dataset_id = "syn12345678"
file_id = "syn87654321"

# Get the dataset
dataset = Dataset(dataset_id).get()

# Create a reference to the file and add it to the dataset
file_ref = File(id=file_id)
dataset.add_item(file_ref)

# Store the updated dataset
dataset.store()

print(f"✓ Added file {file_id} to dataset {dataset_id}")
```

#### 2. Create Link File Entity

```python
import synapseclient
from synapseclient.models import File
import tempfile
import os

syn = synapseclient.Synapse()
syn.login()

# Create temporary placeholder file
temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt')
temp_file.write("External link placeholder")
temp_file.close()

try:
    # Create file entity with external URL (no upload)
    link_file = File(
        parent_id="syn12345678",
        name="External GEO Dataset",
        path=temp_file.name,
        external_url="https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE12345",
        synapse_store=False  # Don't upload the file
    )

    # Add annotations
    link_file.annotations = {
        "dataType": "transcriptomics",
        "fileFormat": "CEL",
        "platform": "Affymetrix"
    }

    # Store
    stored = link_file.store()
    print(f"✓ Created link file: {stored.id}")

finally:
    # Clean up temp file
    os.unlink(temp_file.name)
```

#### 3. Add Link File to Dataset

```python
import synapseclient
from synapseclient import Dataset
from synapseclient.models import File
import tempfile
import os

syn = synapseclient.Synapse()
syn.login()

dataset_id = "syn12345678"

# Create link file
temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt')
temp_file.write("External link")
temp_file.close()

try:
    link_file = File(
        parent_id=dataset_id,  # Can be dataset or project
        name="Related Study",
        path=temp_file.name,
        external_url="https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE99999",
        synapse_store=False
    ).store()

    # Add to dataset
    dataset = Dataset(dataset_id).get()
    file_ref = File(id=link_file.id)
    dataset.add_item(file_ref)
    dataset.store()

    print(f"✓ Created and added link file {link_file.id} to dataset")

finally:
    os.unlink(temp_file.name)
```

#### 4. Create Link Dataset

```python
import synapseclient
from synapseclient import Dataset

syn = synapseclient.Synapse()
syn.login()

# Create dataset with URL annotation
dataset = Dataset(
    name="External GEO Reference",
    parent_id="syn68702804",
    annotations={
        "url": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE12345",
        "studyName": "Gene Expression Study",
        "dataType": ["transcriptomics"],
        "species": ["Homo sapiens"]
    }
)

stored_dataset = dataset.store()
print(f"✓ Created link dataset: {stored_dataset.id}")
```

---

## Testing Checklist

Before testing, activate the environment:
```bash
mamba activate amp-als
```

### Test 1: Generate Template
```bash
python synapse_dataset_manager.py generate-template --type Clinical
ls -la annotations/clinical_dataset_template.json
```

### Test 2: Link Dataset (Dry Run)
```bash
python synapse_dataset_manager.py create \
  --dataset-name "Test Link Dataset" \
  --link-dataset

# Edit annotations/Test_Link_Dataset_dataset_annotations.json
# Add "url": "https://example.com/data"

python synapse_dataset_manager.py create \
  --dataset-name "Test Link Dataset" \
  --link-dataset \
  --from-annotations
```

### Test 3: Add Link File (Dry Run)
```bash
python synapse_dataset_manager.py add-link-file \
  --name "Test Link" \
  --url "https://example.com/test.txt"
```

### Test 4: Add Link File to Dataset (Execute)
```bash
# Replace syn67890 with your actual dataset ID
python synapse_dataset_manager.py add-link-file \
  --name "GEO Reference" \
  --url "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE12345" \
  --dataset-id syn67890 \
  --annotations '{"dataType": "transcriptomics"}' \
  --execute
```

---

## Summary

Three new features have been added to the Synapse Dataset Manager:

1. **Link Datasets**: Create datasets that reference external URLs without files
   - Config: `link_dataset: true`
   - CLI: `--link-dataset`
   - Requires: `url` annotation field

2. **Generate Template**: Create empty dataset annotation templates
   - Command: `generate-template`
   - Types: `Clinical`, `Omic`, `Dataset`
   - No Synapse connection required

3. **Add Link File**: Create file entities with external URL references
   - Command: `add-link-file`
   - Creates File with `external_url` and `synapse_store=False`
   - Can be added to datasets

All features support both CLI and config-based workflows and maintain backward compatibility with existing functionality.

**Remember to activate the mamba environment before testing:**
```bash
mamba activate amp-als
```
