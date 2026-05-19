# JSON Schema LSP Autocompletion for Annotation Templates

## Overview

Annotation templates can leverage JSON Schema to provide autocompletion of allowed enum values directly in your editor via the JSON Language Server (jsonls). When editing a template field that has a defined set of permissible values in the schema, triggering completion will show all allowed options.

## How It Works

Each annotation template includes a `$schema` key that points to the relevant JSON schema file. The JSON LSP reads this schema and provides:

- **Autocompletion** of enum values when filling in fields
- **Validation** errors if a value is not in the allowed set
- **Hover info** with field descriptions from the schema

## Schema Types

There are two template formats, each requiring a different schema reference:

### Flat (Dataset-Level) Templates

Properties are at the root level. Point `$schema` directly to the schema:

```json
{
  "$schema": "../json-schemas/ClinicalDataset.json",
  "assay": [""],
  "dataType": [""],
  ...
}
```

### Nested (File-Level) Templates

Properties are nested under `synID -> filename`. Point `$schema` to a `*Nested.json` wrapper schema:

```json
{
  "$schema": "../json-schemas/ClinicalFileNested.json",
  "syn12345678": {
    "data_file.csv": {
      "assay": [""],
      "dataType": [""],
      ...
    }
  }
}
```

## Schema Mapping by Type

| `--type` flag | Dataset template (flat) | File template (nested) |
|---------------|------------------------|----------------------|
| `Clinical` | `ClinicalDataset.json` | `ClinicalFileNested.json` |
| `Omic` | `OmicDataset.json` | `OmicFileNested.json` |
| `Dataset`/`File` (default) | `Dataset.json` | `FileNested.json` |

## Automatic `$schema` Injection

When generating new templates via `synapse_dataset_manager.py`, the `$schema` key is automatically added based on the `--type` flag:

```bash
# Dataset template with Clinical schema
python synapse_dataset_manager.py generate-template --type Clinical

# File templates with Omic schema
python synapse_dataset_manager.py generate-file-templates --folder syn12345 --type Omic

# General schema (default)
python synapse_dataset_manager.py generate-template --type Dataset
```

## Adding `$schema` to Existing Templates

For pre-existing templates, add `$schema` as the first key in the JSON file. The path is relative from the template file to the `json-schemas/` directory.

Examples based on directory depth:

| Template location | `$schema` value |
|-------------------|----------------|
| `annotations/foo_dataset_annotations.json` | `../json-schemas/ClinicalDataset.json` |
| `annotations/abbvie/foo_file_templates.json` | `../../json-schemas/OmicFileNested.json` |
| `annotations/all_als/dec-release/foo_file_annotations.json` | `../../../json-schemas/ClinicalFileNested.json` |

## Nested Wrapper Schemas

The `*Nested.json` wrapper schemas exist because file-level templates have two extra levels of nesting (`synID -> filename -> properties`). Each wrapper uses `additionalProperties` to tell the LSP that the actual field definitions are two levels deep:

- `FileNested.json` -> references `File.json`
- `ClinicalFileNested.json` -> references `ClinicalFile.json`
- `OmicFileNested.json` -> references `OmicFile.json`

These wrappers are located in `json-schemas/` alongside the base schemas.

## Empty String Handling

By default, JSON Schema flags `""` as invalid for enum fields. Since annotation templates often have blank values (unfilled or not applicable), the Makefile includes a post-processing step that transforms every `enum` field to also accept empty strings:

```
"enum": ["value1", "value2"]  →  "anyOf": [{"enum": ["value1", "value2"]}, {"const": ""}]
```

This is applied automatically via the `JQ_ALLOW_EMPTY` variable in the Makefile during schema generation (`make all`). No manual schema edits are needed.

## Fuzzy-Matched Enum Suggestions

When you enter an invalid enum value, the default jsonls behavior is to show the full list of allowed values, which is unhelpful for schemas with hundreds of options. A custom enhancement in `~/.config/nvim/lua/config/autocmds.lua` replaces this with fuzzy-matched suggestions.

### How it works

1. The enhancement intercepts jsonls pull diagnostics (`textDocument/diagnostic`)
2. For enum mismatch errors (error code 1), it extracts the invalid value from the buffer
3. It normalizes both the entered value and all allowed enum values (lowercase, strip non-alphanumeric characters) before fuzzy matching — so `rna_seq` matches `RNA-seq`, `whole_genome_seq` matches `whole genome sequencing`, etc.
4. The diagnostic message is rewritten to show the top 5 closest matches instead of the full enum list

**Before:**
```
Value is not accepted. Valid values: "2D AlamarBlue absorbance", "2D AlamarBlue fluorescence", "3D confocal imaging", ...
```

**After:**
```
Value "rna_seq" is not accepted. Did you mean: "RNA-seq", "rnaSeq"?
```

### Quick-fix keymap

Press `<leader>ce` on a line with an enum error to open a picker:
- Fuzzy-matched suggestions appear first (marked "suggested")
- All remaining valid values are listed below
- Selecting a value replaces the invalid one in-place

### Why normalized matching

Annotation values often differ from schema enums by case, separators, or abbreviation style:

| You typed | Schema value | Normalized form |
|-----------|-------------|----------------|
| `rna_seq` | `RNA-seq` | `rnaseq` |
| `whole_genome_seq` | `whole genome sequencing` | `wholegenomesequencing` |
| `snp` | `SNP` | `snp` |

Standard fuzzy matching (`vim.fn.matchfuzzy`) fails on these because it's case- and separator-sensitive. The normalization step strips all non-alphanumeric characters and lowercases before matching, then returns the original un-normalized enum values.

## Editor Setup (Neovim)

The JSON LSP extra is enabled in `~/.config/nvim/lua/config/lazy.lua`:

```lua
{ import = "lazyvim.plugins.extras.lang.json" },
```

The fuzzy enum enhancement is configured in `~/.config/nvim/lua/config/autocmds.lua` and activates automatically when jsonls attaches to a JSON buffer. No additional LSP configuration is needed — jsonls natively reads the `$schema` key from each file.
