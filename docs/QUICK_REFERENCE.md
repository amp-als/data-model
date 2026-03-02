# Quick Reference - New Features

## Setup

```bash
# IMPORTANT: Activate environment first
mamba activate amp-als
```

## 1. Generate Template

```bash
# Generate empty dataset annotation template
python synapse_dataset_manager.py generate-template --type Clinical
python synapse_dataset_manager.py generate-template --type Omic -o my_template.json
```

## 2. Link Dataset (No Files)

```bash
# Step 1: Generate template
python synapse_dataset_manager.py create --dataset-name "My Link Dataset" --link-dataset

# Step 2: Edit annotations/My_Link_Dataset_dataset_annotations.json
# Add: "url": "https://example.com/external-data"

# Step 3: Create dataset
python synapse_dataset_manager.py create \
  --dataset-name "My Link Dataset" \
  --link-dataset \
  --from-annotations \
  --execute
```

### Config-based:

```yaml
# config.yaml
datasets:
  MY_LINK_DATASET:
    dataset_name: "External GEO Dataset"
    dataset_type: "Omic"
    link_dataset: true
```

```bash
python synapse_dataset_manager.py create --use-config MY_LINK_DATASET
# Edit annotations, add url field
python synapse_dataset_manager.py create --use-config MY_LINK_DATASET --from-annotations --execute
```

## 3. Add Link File (External URL Reference)

```bash
# Basic usage (creates in project)
python synapse_dataset_manager.py add-link-file \
  --name "GEO Dataset" \
  --url "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE12345" \
  --execute

# Add to specific dataset
python synapse_dataset_manager.py add-link-file \
  --name "External RNA-seq Data" \
  --url "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE12345" \
  --dataset-id syn67890 \
  --execute

# With annotations
python synapse_dataset_manager.py add-link-file \
  --name "Proteomics Data" \
  --url "https://example.com/data.zip" \
  --dataset-id syn67890 \
  --annotations '{"dataType": "proteomics", "platform": "Olink"}' \
  --execute
```

## Python Code Snippets

### Add File to Dataset

```python
from synapseclient import Dataset
from synapseclient.models import File

dataset = Dataset("syn12345").get()
file_ref = File(id="syn67890")
dataset.add_item(file_ref)
dataset.store()
```

### Create Link File

```python
from synapseclient.models import File
import tempfile, os

temp = tempfile.NamedTemporaryFile(mode='w', delete=False)
temp.write("placeholder")
temp.close()

try:
    link = File(
        parent_id="syn12345",
        name="External Link",
        path=temp.name,
        external_url="https://example.com/data",
        synapse_store=False
    ).store()
finally:
    os.unlink(temp.name)
```

## Help Commands

```bash
# Main help
python synapse_dataset_manager.py --help

# Command-specific help
python synapse_dataset_manager.py generate-template --help
python synapse_dataset_manager.py add-link-file --help
python synapse_dataset_manager.py create --help
```
