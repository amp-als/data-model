# New Features - Synapse Dataset Manager

This directory contains documentation for three new features added to `synapse_dataset_manager.py`.

## 📚 Documentation Files

1. **[NEW_FEATURES_DOCUMENTATION.md](NEW_FEATURES_DOCUMENTATION.md)** - Comprehensive guide
   - Detailed usage examples
   - Configuration examples
   - Code snippets
   - Testing instructions

2. **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - Quick reference guide
   - Quick command examples
   - Common use cases
   - Python code snippets

3. **[IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)** - Technical details
   - Code changes summary
   - Functions added/modified
   - Design decisions
   - Backward compatibility notes

## 🚀 Quick Start

### Setup
```bash
# REQUIRED: Activate environment before testing
mamba activate amp-als
```

### Test Commands
```bash
# 1. Generate dataset template
python synapse_dataset_manager.py generate-template --type Clinical

# 2. Create link dataset (no files)
python synapse_dataset_manager.py create --dataset-name "Test" --link-dataset

# 3. Add external URL reference to dataset
python synapse_dataset_manager.py add-link-file \
  --name "GEO Dataset" \
  --url "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE12345" \
  --dataset-id syn67890 \
  --execute
```

## ✨ New Features

### 1. Link Datasets
Create datasets that reference external URLs without uploading files to Synapse.

**Use Case:** Reference GEO datasets, dbGaP studies, or other external data sources.

**CLI:**
```bash
python synapse_dataset_manager.py create --link-dataset \
  --dataset-name "External GEO Dataset"
```

**Config:**
```yaml
datasets:
  MY_LINK_DATASET:
    dataset_name: "External Dataset"
    link_dataset: true
```

### 2. Generate Template
Generate empty dataset annotation templates without connecting to Synapse.

**Use Case:** Preview available fields, create templates for link datasets.

**CLI:**
```bash
python synapse_dataset_manager.py generate-template --type Clinical
python synapse_dataset_manager.py generate-template --type Omic
python synapse_dataset_manager.py generate-template --type Dataset
```

### 3. Add Link File
Create file entities that reference external URLs (no upload).

**Use Case:** Add external references to datasets, mix local and external data.

**CLI:**
```bash
python synapse_dataset_manager.py add-link-file \
  --name "External RNA-seq Data" \
  --url "https://example.com/data" \
  --dataset-id syn67890 \
  --annotations '{"dataType": "transcriptomics"}' \
  --execute
```

## 📖 Help Commands

```bash
# Main help
python synapse_dataset_manager.py --help

# Command-specific help
python synapse_dataset_manager.py generate-template --help
python synapse_dataset_manager.py add-link-file --help
python synapse_dataset_manager.py create --help
```

## 🔍 Where to Find What

| Need | Documentation File |
|------|-------------------|
| How to use features | [NEW_FEATURES_DOCUMENTATION.md](NEW_FEATURES_DOCUMENTATION.md) |
| Quick examples | [QUICK_REFERENCE.md](QUICK_REFERENCE.md) |
| Technical details | [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) |
| Code examples | [NEW_FEATURES_DOCUMENTATION.md](NEW_FEATURES_DOCUMENTATION.md) - Code Snippets section |
| Config examples | [NEW_FEATURES_DOCUMENTATION.md](NEW_FEATURES_DOCUMENTATION.md) - Configuration Examples section |

## ⚠️ Important Notes

1. **Environment:** Always activate `mamba activate amp-als` before testing
2. **Dry-run:** Commands run in dry-run mode by default. Use `--execute` to apply changes
3. **Backward Compatible:** All existing workflows remain unchanged
4. **Link Datasets:** Must include `url` annotation field
5. **External Links:** Use `File` with `synapse_store=False` for external URL references

## 🧪 Testing

See [NEW_FEATURES_DOCUMENTATION.md](NEW_FEATURES_DOCUMENTATION.md) - Testing Checklist section for complete testing guide.

Quick test:
```bash
# Activate environment
mamba activate amp-als

# Test syntax
python -m py_compile synapse_dataset_manager.py

# Test commands (dry-run)
python synapse_dataset_manager.py generate-template --type Clinical
python synapse_dataset_manager.py create --dataset-name "Test" --link-dataset
python synapse_dataset_manager.py add-link-file --name "Test" --url "https://example.com"
```

## 📝 Summary

Three new features for flexible dataset management:

| Feature | Purpose | Key Benefit |
|---------|---------|-------------|
| **Link Datasets** | Reference external data | No file upload needed |
| **Generate Template** | Preview schemas | See fields before creation |
| **Add Link File** | Add external references | Mix local & external data |

All features support:
- ✅ CLI and config workflows
- ✅ Dry-run mode
- ✅ Comprehensive error handling
- ✅ Full documentation
- ✅ Backward compatibility

## 🤝 Contributing

When updating these features:
1. Update relevant documentation
2. Add examples to help text
3. Include error handling
4. Maintain backward compatibility
5. Add to testing checklist

## 📧 Support

For questions or issues:
1. Check [NEW_FEATURES_DOCUMENTATION.md](NEW_FEATURES_DOCUMENTATION.md) for detailed usage
2. Review [QUICK_REFERENCE.md](QUICK_REFERENCE.md) for examples
3. See [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) for technical details

---

**Last Updated:** 2026-02-05
**Version:** 1.0
**Environment:** amp-als (mamba)
