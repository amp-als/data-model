# Clean PHI/PII Columns from Versioned Synapse Files

`scripts/clean_phi_files.py` is a standalone script for removing reviewed PHI/PII
columns from every version of files in a Synapse folder. It does not import or
invoke `synapse_dataset_manager`.

> **Safety model:** The workflow is intentionally two-step. Step 1 lists folder
> metadata only; it does **not** download, open, or inspect file bytes. Downloading
> begins only in step 2 after a reviewer has filled in the column-removal map.

## Supported files

- CSV
- TSV
- XLSX
- XLSM

Column names must exactly match the source header. The script stops with an error
if a designated column is absent from any version it is asked to clean. Source
Synapse files and their version histories are never changed.

## Install and authenticate

```bash
pip install -r requirements_clean_phi_files.txt
export SYNAPSE_AUTH_TOKEN="<personal-access-token>"
```

Alternatively, provide `--auth-token <token>` or use Synapse's normal local
credential discovery (`synapse login`). Run the script from the repository root:

```bash
python scripts/clean_phi_files.py --help
```

## Step 1: Generate a reviewed column map

Generate a recursive metadata-only scaffold for the input folder:

```bash
python scripts/clean_phi_files.py \
  --folder syn77348789 \
  --write-column-map annotations/files_to_clean_columns.json
```

The default map uses Synapse IDs because filenames can repeat in different
subfolders:

```json
{
  "syn12345678": [],
  "syn23456789": []
}
```

Fill each array with the exact headers to remove, then have the map reviewed:

```json
{
  "syn12345678": ["patient_name", "date_of_birth"],
  "syn23456789": ["email", "phone_number"]
}
```

Use `--map-key name` only if every filename is unique. A map can also use a
unique filename as a key during step 2, but Synapse IDs are recommended.

An empty array means that file is copied unchanged; it is still processed for
all versions. This lets the reviewed map explicitly cover every input file.

## Step 2A: Export cleaned versions locally

```bash
python scripts/clean_phi_files.py \
  --folder syn77348789 \
  --column-map annotations/files_to_clean_columns.json \
  --output-dir ./cleaned_files
```

Every source version is downloaded and cleaned. Local output is organized by
source ID and version number, for example:

```text
cleaned_files/
  syn12345678/
    v1_demographics.csv
    v2_demographics.csv
  syn23456789/
    v1_contacts.xlsx
```

Review these output files before distributing or uploading them.

## Step 2B: Upload as one new Synapse File entity

Add `--upload-folder`, `--merged-name`, and `--execute` to upload each cleaned
version as the version history of one new File entity. The input entities remain
unchanged.

```bash
python scripts/clean_phi_files.py \
  --folder syn77348789 \
  --column-map annotations/files_to_clean_columns.json \
  --output-dir ./cleaned_files \
  --upload-folder synTARGET_FOLDER \
  --merged-name "Files_To_Remove_and_Clean_cleaned.csv" \
  --execute
```

Versions are uploaded in source Synapse-ID order and then ascending source-version
order. If local copies are not needed, omit `--output-dir`; cleaned temporary
files are deleted after they are uploaded:

```bash
python scripts/clean_phi_files.py \
  --folder syn77348789 \
  --column-map annotations/files_to_clean_columns.json \
  --upload-folder synTARGET_FOLDER \
  --merged-name "Files_To_Remove_and_Clean_cleaned.csv" \
  --execute
```

## Important notes

- `--execute` is required only for uploads. Local cleaning has no write operation
  against Synapse.
- The generated map contains every file found recursively. The step-2 map controls
  which files are processed; retain all generated keys to process the whole folder.
- The script preserves tabular values other than removed columns. It does not
  perform PHI/PII detection; reviewers supply the designated column names.
- Do not use this workflow for unsupported file formats. It fails rather than
  attempting to parse or alter them.
