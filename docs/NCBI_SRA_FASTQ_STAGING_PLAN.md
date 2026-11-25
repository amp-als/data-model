# NCBI SRA FASTQ staging plan: NYGC ALS GEO studies

## Agent execution directive

You are the implementation and operations agent for this workflow. **Carry out the work described in this document; do not merely summarize it, propose commands, or produce a plan.**

Your responsibilities are to:

1. Set up the two required conda environments and verify the existing Synapse configuration.
2. Implement the standalone, resumable SRA-transfer workflow and its Synapse/template handoff.
3. Implement the required SQLite state store, provenance artifacts, QC, approval gates, and reporting.
4. Run the mandatory read-only preflight and resolve ordinary setup/tooling problems found by it.
5. Present the preflight go/no-go report and stop before any raw-read action if it contains a no-go item.
6. After preflight approval, execute the bounded pilot through FASTQ preparation and validation, but stop before upload for user file review and explicit approval.
7. After the user records approval for a study, perform that study's approved serial upload work, generate/fill/validate the standard `synapse_dataset_manager` templates, apply annotations, verify uploads, and report the result.
8. Continue study by study until this four-study scope is complete, stopping only at the explicit user-review/approval gates or on a documented hard failure.

Do not ask for confirmation for routine implementation choices. Make conservative, reproducible choices consistent with this document, record them in provenance, and report them. Do not start raw-read retrieval, create FASTQ upload folders, or upload FASTQs before the stated preflight and user-approval gates. Reference-genome selection, alignment, quantification, and all downstream analysis are out of scope.

## Scope

Stage NCBI-SRA-derived gzipped FASTQ files for the four new NYGC ALS studies only.

| GEO study | Synapse staging folder | Runs | Layout |
|---|---:|---:|---|
| GSE272624 | `syn78745358` | 289 | paired-end |
| GSE272626 | `syn78745363` | 266 | paired-end |
| GSE308462 | `syn78745368` | 260 | paired-end |
| GSE122649 | `syn78745373` | 38 | single-end |

This scope is 853 SRA runs and 1,668 expected FASTQ files. Do **not** download raw reads for GSE116622, GSE124439, or GSE153960 without explicit approval.

GSE122649 is included at request but is a subseries of GSE122650, not GSE137810.

## Source policy

- Use **NCBI SRA only** for all raw reads.
- Do **not** use ENA-delivered FASTQs, ENA URLs, or GEO supplementary count files as raw-read input.
- Do **not** use FASTA because it omits base-quality scores.
- Download the NCBI SRA archive for each `SRR` accession, validate it, and extract reproducible FASTQ using a pinned SRA Toolkit version.
- NCBI SRA extraction is reproducible from the archive, but may not be byte-identical to an original sequencing-center submission file.

### Full-quality requirement

NCBI can expose an SRA Lite representation for some runs. SRA Lite may use reduced/binned quality values and is not acceptable for harmonized reprocessing requiring original-quality FASTQ. The implementation must explicitly configure/request the full-quality NCBI SRA representation, not SRA Lite, and must prove this in the pilot before any bulk transfer.

For every pilot archive, record the archive format/quality mode and demonstrate from the extracted FASTQ quality distribution that it is not a four-level/binned SRA Lite quality representation. A suspected Lite archive or quality-binned output is a no-go: retain the artifacts, do not upload, and resolve the NCBI SRA Toolkit full-quality retrieval configuration before proceeding.

## Local layout and storage

All working data must reside under `~/data` (not the repository and not `/tmp`). Suggested layout:

```text
~/data/
├── ncbisra-nygc-als/
│   ├── cache/                  # NCBI SRA prefetch cache / .sra archives
│   ├── scratch/                # fasterq-dump temporary files
│   ├── fastq/                  # current run's FASTQ output only
│   ├── manifests/              # durable status, checksums, provenance
│   ├── logs/                   # one log per run
│   └── failed/                 # retained failed-run artifacts
```

The instance already has 1 TB of local storage available; no additional volume or mount is required. Create and use `~/data` on that existing storage. The pipeline is initially serial: it must not start a second run until the prior run has uploaded and been verified. This limits local storage to one run's SRA archive, temporary conversion files, and output FASTQ files.

## Environment setup

Use conda/mamba environments; do not install bioinformatics tools system-wide.

1. Install Miniforge/Mambaforge in the home directory (for example, `~/miniforge3`) if `conda` is not already available. Do not install conda under `~/data`.
2. Create two separate environments:

   ```bash
   # NCBI archive retrieval, validation, FASTQ extraction, compression, and local checks
   mamba create -n nygc-sra-transfer -c conda-forge -c bioconda \
     python=3.10 sra-tools pigz pysam seqkit

   # Synapse folder/entity operations, schema/template validation, and uploads.
   # This is the repository-standard Synapse/data-model environment.
   mamba create -n amp-als -c conda-forge -c bioconda \
     python=3.10 synapseclient jsonschema pandas requests
   ```

3. The instance's `~/.synapseConfig` will already be configured. Use it only from the `amp-als` environment for authenticated uploads; do not overwrite it, commit it, or place Synapse credentials in scripts or manifests.

4. Keep the environments separate:

   ```bash
   # SRA retrieval/extraction
   mamba run -n nygc-sra-transfer ...

   # synapse_dataset_manager template workflow, validation, and Synapse upload
   mamba run -n amp-als python -m synapse_dataset_manager ...
   ```

   The SRA-transfer process must write its durable status/checksum manifest under `~/data/ncbisra-nygc-als/manifests/`. The Synapse process reads that manifest, uses `synapse_dataset_manager` to generate and validate templates, uploads only validated completed outputs, and records Synapse entity IDs back into it. Do not place Synapse credentials or upload dependencies in the transfer environment.

5. Record exact versions of both environments' tools, the transfer script, and the uploader/template script in the provenance manifest. Save exported conda environment specifications under `~/data/ncbisra-nygc-als/manifests/`.

## Data-model repository and annotation templates

The data-model repository will be available at `~/github/data-model`. Use the checked-out local repository, not mutable raw GitHub URLs, as the schema source. Record the repository commit SHA in the provenance document.

Use the generated schemas in that checkout:

```text
~/github/data-model/json-schemas/GEOFile.json
~/github/data-model/json-schemas/GEODataset.json
```

- **GEOFile** is the schema for every uploaded FASTQ file. It inherits the SRA identifiers and adds the GEO `GSE`/`GSM` identifiers.
- **GEODataset** is the schema for one dataset-level annotation template per GEO study; it is not a per-FASTQ schema. The current GEO locations are staging folders, not Synapse Dataset entities, so retain these as validated templates for later application to the corresponding released Dataset rather than applying GEODataset annotations to a staging folder.

Use the standard `synapse_dataset_manager` workflow rather than hand-creating annotation JSON:

1. Generate one dataset template per GSE from the local checkout:

   ```bash
   mamba run -n amp-als python -m synapse_dataset_manager generate-template \
     --type GEODataset --output <template-path>
   ```

2. After FASTQ entities are uploaded to the study's `FASTQ (NCBI SRA)` folder, generate a Synapse-backed GEO file template:

   ```bash
   mamba run -n amp-als python -m synapse_dataset_manager generate-file-templates \
     --folder <fastq-folder-synid> --type GEOFile \
     --metadata <joined-file-metadata.csv> --skip-ai --refresh-walkthrough \
     --output <template-path>
   ```

3. Deterministically fill the manager-generated file template by matching Synapse entity ID/filename to the joined metadata; do not use AI. Preview validation/application first, then apply it through the manager:

   ```bash
   mamba run -n amp-als python -m synapse_dataset_manager apply-file-annotations \
     --annotations-file <filled-template.json> --dry-run
   mamba run -n amp-als python -m synapse_dataset_manager apply-file-annotations \
     --annotations-file <filled-template.json> --execute
   ```

Retain generated, filled, reviewed, and applied templates in the study's provenance/metadata area. Do not edit the data model or generated schemas for this workflow.

The joined per-file metadata must combine the staged `<GSE>_sra_run_manifest.csv`, `<GSE>_sample_metadata.csv`, and transfer output/checksum manifest. It must preserve, where available, `GSE`, `GSM`, `SRP`, `SRX`, `SRR`, `BioProject`, `BioSample`, library layout, file format, read pair, subject metadata, tissue metadata, and source/provenance fields. Do not invent annotations when a value is absent; leave schema-allowed fields blank or omit them according to the manager-generated template format.

## Synapse layout

The existing study folders already contain metadata and run manifests. Under each study folder, create a child folder named exactly:

```text
FASTQ (NCBI SRA)
```

Do not put FASTQs directly next to the metadata files.

Use the staged `<GSE>_sra_run_manifest.csv` and `<GSE>_sample_metadata.csv` as the approved run list and sample-to-run mapping.

Uploaded files must use these names:

- paired-end: `SRRxxxx_1.fastq.gz`, `SRRxxxx_2.fastq.gz`
- single-end: `SRRxxxx_1.fastq.gz`

Use the completed, schema-validated **GEOFile** annotation template as the source for each uploaded FASTQ's Synapse annotations; do not hard-code a parallel annotation mapping in the uploader. At minimum, when values are available and schema-supported, the template must carry GEO/SRA accessions, source (`NCBI SRA`), library layout, read pair/type, output SHA-256, retrieval date, and SRA Toolkit version.

## Human review and upload approval gate

The workflow must separate FASTQ preparation from upload. For each study, first run a **prepare-only review batch**: download from NCBI SRA, validate, extract, compress, and checksum a small representative set of runs, but do not create Synapse FASTQ folders or upload any FASTQ files. Stop and present the local file paths, checksums, file sizes, gzip validation, read-layout results, and logs for user review.

The user must explicitly approve the prepared files for that study before any upload begins. Record the approval (reviewer, UTC timestamp, study, approved SRRs/files, and approval note) in the durable manifest. The uploader must refuse to upload a file without recorded approval for its study.

A full-study local review before upload is **not feasible** on the available 1 TB disk: GSE272624 alone is expected to produce more than 1 TiB of gzipped FASTQ. Therefore review/approval must be based on a bounded representative batch (or successive bounded batches), after which the approved study can use the normal serial prepare → upload → verify → delete loop. Do not retain an entire study locally while waiting for review.

Required modes in addition to the standard transfer mode:

- `--prepare-only`: prepare and validate explicitly selected review SRRs without uploading or creating Synapse folders;
- `--record-approval`: record an explicit user approval for the reviewed study/files in the durable manifest;
- `--upload-approved`: upload only files with recorded approval; refuse all other files.

## Per-run workflow

For each approved run:

1. Check the durable status manifest. Skip only runs already proven fully uploaded and validated.
2. Check available local disk space and reserve enough space for the archive, `fasterq-dump` scratch, uncompressed FASTQ, compressed FASTQ, and safety margin.
3. Download/resume the archive from NCBI SRA with `prefetch`.
4. Run `vdb-validate` on the archive. Stop the run if validation fails.
5. Extract reads with `fasterq-dump` using the manifest's declared layout:
   - paired-end: split R1/R2 output;
   - single-end: one output file.
6. Fail rather than silently accepting unexpected extra/singleton output files.
7. Compress output using `pigz` or gzip.
8. Validate gzip integrity, calculate SHA-256, and record output sizes.
9. Update the per-file GEOFile template with the final filename, read-pair designation, checksums, sizes, and retrieval/conversion provenance; validate it against the local `GEOFile.json` schema.
10. If the file is part of a review batch, stop here and await recorded user approval. Otherwise require that its study has a recorded user approval before upload.
11. Upload the expected output files to that study's `FASTQ (NCBI SRA)` Synapse folder using the validated template annotations.
12. Verify each uploaded file has a Synapse entity ID, expected name, expected size, and applied template annotations recorded in the transfer manifest.
13. Only then mark the run complete and delete its local archive, scratch, and FASTQ files.
13. Retain failed-run artifacts and logs under `~/data/ncbisra-nygc-als/failed/` for diagnosis.

## Transfer resilience, QC, disk safety, recovery, and cost controls

### NCBI retrieval resilience

- Retrieve only one SRR at a time initially.
- Use resumable NCBI SRA retrieval and preserve the partially retrieved archive/cache for retry.
- Retry transient network or service failures at most three times with exponential backoff and jitter; record every attempt, HTTP/tool error, and retry timestamp.
- Treat `vdb-validate` failure, an unexpected archive identity, or repeated retrieval failure as a terminal failed run requiring review. Do not loop indefinitely or substitute another source.
- Do not begin a different run while a failed run is awaiting a retry decision.

### Read/output QC and header review

- For every output FASTQ: run gzip integrity validation, capture `seqkit stats`, and record sequence/read counts, total bases, and file size.
- For paired runs: require identical R1/R2 sequence counts. A mismatch is a failed run, not a warning.
- For the pilot only: run FastQC on each output FASTQ and retain the reports. Do not trim, filter, rename reads, or otherwise modify sequence data.
- Record a representative set of FASTQ headers from the pilot outputs and the exact `fasterq-dump` invocation used. Do not transform headers after SRA extraction.

### Unexpected SRA extraction outputs

- Establish the exact `fasterq-dump` options in the pilot and record them in provenance.
- A paired manifest row must yield exactly one R1 and one R2 FASTQ; a single-end row must yield exactly one FASTQ.
- An unexpected `_3`/orphan/technical-read file, empty output, extra output, or filename mismatch is a hard stop for that SRR. Preserve all artifacts and logs, mark the run `failed`, and require review before choosing a scientifically appropriate extraction policy.
- Never silently discard technical or orphan reads.

### Disk safety

- Before beginning each run, require at least **250 GiB free** in `~/data`; the pilot may increase this threshold but must never lower it.
- Reserve space for the `.sra` archive, SRA Toolkit temporary files, uncompressed FASTQ, compressed FASTQ, logs, and a safety margin before calling `prefetch`.
- Measure peak space for every pilot run. Derive a conservative per-run reservation from the largest observed peak plus margin, and use that reservation to reject unsafe work before it starts.
- If free space falls below the reservation during extraction, stop before starting any additional run and retain recoverable artifacts for review.

### Atomic recovery and idempotence

- Use SQLite as the authoritative durable status store, not an editable CSV. CSV/TSV manifests may be exported for review but are not the resume authority.
- Store run state transitions, checksums, local paths, exact commands, timestamps, errors, approval records, and Synapse entity IDs transactionally.
- Use atomic file writes/renames for exported manifests and provenance documents.
- Before a retry or upload, query the target Synapse folder for a same-name entity. Treat a matching recorded entity ID/checksum/size as complete; treat a conflicting same-name entity as a hard collision requiring review. Never create duplicate names to bypass a conflict.
- A run is complete only after its validated outputs, template application, Synapse IDs, sizes, checksums, and user approval are committed to SQLite.

### Cost and throughput accounting

- Record per-run and cumulative NCBI bytes retrieved, compressed FASTQ bytes produced/uploaded, elapsed download/extraction/compression/upload time, retry count, and peak scratch consumption.
- Record instance type, EBS/local storage configuration, and UTC start/stop times in provenance.
- After the pilot, report measured NCBI and Synapse throughput, estimated wall-clock duration for each study, projected instance/EBS runtime, and projected Synapse storage growth before requesting bulk approval.

## Required durable manifests

Create a durable SQLite status store under `~/data/ncbisra-nygc-als/manifests/` with one row per expected FASTQ. It must include:

- GEO series, GSM, SRX, SRR
- library layout and read pair/type
- NCBI source/accession
- local output path and Synapse destination folder
- SRA Toolkit version and exact extraction command
- archive-validation result
- output size and SHA-256
- Synapse entity ID and upload timestamp
- state: `pending`, `downloaded`, `extracted`, `validated`, `uploaded`, or `failed`
- failure message, where applicable

Also produce and upload a study-level transfer manifest and a top-level README/provenance document. The README must explicitly state that all raw reads came from NCBI SRA and that ENA-delivered FASTQs were not used.

## Required implementation interface

Create a standalone script under `scripts/`; do not modify `synapse_dataset_manager.py`. It must support:

- `--preflight`: perform the mandatory read-only prerequisite inventory and write its report; it must not create folders, download raw reads, or upload files;
- `--dry-run`: validate inputs and print planned actions without creating folders, downloading, or uploading;
- `--pilot`: process an explicit list of SRR accessions;
- `--prepare-only`: prepare and validate selected review SRRs but do not create Synapse FASTQ folders or upload;
- `--record-approval`: persist explicit user approval for named studies/SRRs after review;
- `--upload-approved`: upload only files whose approval is present in the durable manifest;
- `--study GSE...`: restrict processing to named studies;
- `--execute`: required for any side effect;
- `--resume`: continue only incomplete/failed work;
- `--max-workers`: default `1`; reject greater concurrency unless disk capacity is explicitly confirmed;
- configurable `--data-dir ~/data/ncbisra-nygc-als`;
- configurable manifest/state directory.

Never store credentials, Synapse tokens, raw FASTQs, SRA archives, or transient status/log files in git.

## Mandatory preflight inventory (before any raw-read action)

Before creating FASTQ folders, downloading SRA archives, extracting reads, or uploading FASTQs, implement and run a read-only `--preflight` check. It must produce a dated report under `~/data/ncbisra-nygc-als/manifests/` and clearly classify every prerequisite as **present**, **missing**, **misconfigured**, or **requires approval**.

The preflight must check all of the following without downloading raw reads:

1. **Scope and source manifests**
   - Confirm the four approved GSE accessions, staging-folder IDs, expected run counts, and expected layouts in this plan.
   - Authenticate to Synapse from the `amp-als` environment and confirm that each staged run manifest and sample metadata file is accessible.
   - Confirm the manifests resolve to exactly 853 unique SRR runs, 815 paired-end runs, 38 single-end runs, and 1,668 expected FASTQs.
   - Detect duplicate SRRs, missing GSM/SRX/SRR mappings, unexpected library layouts, and runs already present in a target FASTQ folder.

2. **Repository and schema tooling**
   - Confirm `~/github/data-model` exists, is readable, and contains `synapse_dataset_manager`, `json-schemas/GEOFile.json`, and `json-schemas/GEODataset.json`.
   - Record the repository commit SHA and report whether the checkout has uncommitted changes; do not alter schemas.
   - Confirm the `amp-als` environment can import `synapseclient` and run `python -m synapse_dataset_manager --help`, `generate-template --help`, `generate-file-templates --help`, and `apply-file-annotations --help`.

3. **Environments and NCBI tooling**
   - Confirm both `nygc-sra-transfer` and `amp-als` conda environments exist.
   - Confirm `prefetch`, `vdb-validate`, `fasterq-dump`, `pigz`, gzip validation, Python, and checksum tools are available in `nygc-sra-transfer`; record exact versions.
   - Confirm `synapseclient`, `jsonschema`, and required manager dependencies are available in `amp-als`; record exact versions.
   - Confirm `~/.synapseConfig` exists with safe permissions, without printing its contents or credentials.

4. **Storage, network, and Synapse authorization**
   - Confirm `~/data` exists on the instance's existing 1 TB storage, is writable, and has adequate free bytes/inodes. Do not mount or provision another volume.
   - Confirm the directory structure in this plan can be created and that scratch/cache/output paths are on the intended storage.
   - Confirm HTTPS connectivity to NCBI SRA and Synapse, but do not retrieve an SRA archive.
   - Confirm the authenticated Synapse principal can create a child `FASTQ (NCBI SRA)` folder and upload files under each of the four staging folders. Do this as a permission/API check only; do not create folders during preflight.
   - Report the configured concurrency, conservative per-run disk reservation, and whether it is safe. Default must be one worker.

5. **Annotation workflow readiness**
   - Confirm the manager can generate an empty GEODataset template locally.
   - Confirm that each staged metadata manifest has the fields necessary to fill GEOFile identifiers (`GSE`, `GSM`, `SRP`, `SRX`, `SRR`, BioProject, BioSample) and flag missing fields rather than inventing values.
   - Produce a no-write preview of the joined per-file metadata and the proposed annotation field mapping.

The preflight report must end with an explicit go/no-go decision. A missing prerequisite, missing permission, schema/tool failure, insufficient disk reserve, or unresolved metadata mapping is a **no-go**. Do not proceed to folder creation, pilot, or bulk transfer until all no-go items are resolved and the report has been reviewed.

## Pilot gate

Do not start the bulk download immediately. First implement the script and run only a four-run pilot after reviewing its dry run and successful preflight report:

- one small paired-end run;
- one median paired-end run;
- one large paired-end run;
- one GSE122649 single-end run.

Before executing the pilot, report selected SRRs, expected archive sizes, expected disk reservation, output names, exact NCBI commands, and Synapse destination folders.

After the pilot, report:

- peak local scratch use;
- NCBI download throughput;
- conversion and compression duration;
- final gzipped FASTQ sizes;
- Synapse upload throughput;
- archive/output validation results;
- resulting Synapse IDs;
- any header or quality-score observations.

Only start the remaining runs after explicit approval of the pilot results.

## Validation requirements

For every run, require all of the following before marking it complete:

- the run is present in an approved staged run manifest;
- `vdb-validate` passes;
- the observed FASTQ file count matches the library layout;
- each gzipped FASTQ passes gzip integrity testing;
- each FASTQ has a recorded SHA-256;
- each output has a verified Synapse entity ID, stored name, and stored size.

## Deliverables after pilot or bulk execution

Report:

1. created/changed implementation files;
2. exact conda/mamba environment setup commands;
3. exact dry-run, pilot, resume, and eventual bulk commands;
4. Synapse IDs for the new FASTQ folders and uploaded files;
5. total completed, pending, and failed runs/files;
6. a concise operational runbook for monitoring and recovery.
