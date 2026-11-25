# Rebuilding File and Dataset Entities

## Purpose

Use these workflows when replacement File entities must be created because a released
File version history references incorrect content or an obsolete Synapse ID. Rebuilding
Files changes their Synapse IDs, so any historical Dataset snapshots that reference the
old Files must be rebuilt separately to point to the replacement File IDs and pinned
versions.

Existing File and Dataset entities are retained throughout validation. No command in
this workflow deletes an original entity automatically.

**Do not trash or delete old Files until the entire File-level and Dataset-level
rebuild is complete and verified.** Historical Dataset snapshots retain their original
File IDs; the generator needs access to their metadata to resolve replacement versions.
Trashing old Files early can block reconstruction. Preserve the originals through
manifest review, snapshot verification, and any required DOI or migration review.

## File entity rebuild

`generate-file-rebuild-manifest` produces a draft for a single File from explicitly
labeled staging folders; see `docs/QUICK_REFERENCE.md` for a runnable example. The
draft pins the latest version in each folder and needs review before use.

`rebuild-file-entity` rebuilds one or more File version histories from explicitly
listed staging sources.

```bash
mamba run -n amp-als python -m synapse_dataset_manager rebuild-file-entity \
  --manifest rebuild_file_manifest.json \
  --output annotations/file_rebuild_result.json
```

The default is a metadata-only preview. It resolves exact source filenames in the
explicitly listed staging folder IDs and writes a plan without downloading file bytes.
Use `--execute` only after reviewing that plan. Execution requires `--output` for an
atomic, incremental report. Initial File creation is create-only and fails on name
collisions. If a store fails or times out, inspect the report and Synapse before retrying:
the remote outcome may be unknown. The workflow never modifies a Dataset; a legacy
`dataset_id` field is ignored with a warning.

### File rebuild manifest

```json
{
  "output_folder": "synOUTPUT_FOLDER",
  "targets": [
    {
      "key": "corrected_file",
      "output_name": "Corrected release file.csv",
      "source_filename": "raw_source.csv",
      "original_entity_id": "synOLD_RELEASE_FILE",
      "annotation_source_entity_id": "synOLD_RELEASE_FILE",
      "sources": [
        {
          "folder_id": "synSTAGING_RELEASE_1",
          "label": "v1",
          "comment": "Initial release"
        },
        {
          "folder_id": "synSTAGING_RELEASE_2",
          "label": "v2",
          "source_filename": "renamed_raw_source.csv",
          "annotation_source": {
            "entity_id": "synOLD_RELEASE_FILE",
            "version": 2
          }
        }
      ]
    }
  ]
}
```

Source discovery is based only on exact filenames in supplied folders. It does not
infer source files from `viewName`, cohort names, release dates, or project-specific
naming conventions. Annotation selection can be interactive (default) or automatic:

```bash
mamba run -n amp-als python -m synapse_dataset_manager rebuild-file-entity \
  --manifest rebuild_file_manifest.json --execute --annotation-mode interactive \
  --output annotations/file_rebuild_result.json
```

An executed File rebuild report records the original File ID, replacement File ID,
source/replacement version labels, source version dates, MD5 values, and sizes. That
report is input to Dataset-level manifest generation. Set `original_entity_id` explicitly
when the replacement mapping is known; an annotation source does not establish which File
is being replaced. Partial or failed reports cannot generate a Dataset rebuild manifest.

## Dataset entity rebuild (partial execution support)

The Dataset manifest generator accepts a completed File rebuild report or repeatable
replacement folders and File IDs. Candidate selections require interactive review. `rebuild-dataset-entity` defaults to metadata-only preview. Explicit execution
copies the latest wiki hierarchy and markdown. Attachments are not copied; their IDs
and names are reported and users are warned to reattach them manually. Execution has not yet
been validated in an authenticated sandbox. See the quick reference for commands and
partial failure recovery. The policies below describe the intended complete behavior.

Dataset reconstruction is required when a historical Dataset snapshot references a
File ID that has been replaced. Dataset snapshots are immutable; their membership
cannot be edited in place.

The Dataset workflow creates a new Dataset entity in the same Project as the current
source Dataset. The Project is inferred from the source Dataset's `parentId`; an
explicit parent override is reserved for exceptional cases.

### Dataset manifest generation

The Dataset manifest generator reads:

- the current/source Dataset ID;
- historical Dataset snapshots and their pinned `EntityRef(id, version)` members;
- either one File rebuild report, or explicitly supplied replacement folders and/or File IDs.

Report and folder/File candidates can be combined; duplicates are collapsed and each
selection still requires review. Explicit per-snapshot replacements
can be supplied with either mode and take precedence for those members. Report mode
matches the report's original File IDs and version labels; other members remain pinned.
Folder/File mode matches exact filenames and version labels. Every candidate requires
interactive review, including a unique match; missing candidates can be explicitly kept
or aborted. Explicit keeps are recorded in `kept_members`. Version dates and comments
are evidence for manual review, not proof of equivalence. Non-interactive mode fails
rather than guessing.

### Dataset reconstruction policy

For every declared Dataset release/snapshot, the reconstruction must:

1. Read the source Dataset snapshot membership, label, comment, and annotations.
2. Preserve all unchanged pinned member references.
3. Substitute only reviewed old-File to replacement-File ID/version mappings and
   add reviewed pinned File references in `member_additions`, if any.
4. Copy the source Dataset version annotations and apply reviewed overrides.
5. Create a labeled, immutable replacement Dataset snapshot.
6. Verify exact member IDs/versions, label/comment, and Dataset annotations.

### Schema policy

The replacement Dataset uses the latest schema/columns from the source Dataset for
all reconstructed snapshots. The workflow compares the copied schema with the latest
source schema and reports differences. Historical schema changes are intentionally
not recreated.

### Wiki policy

Copy the latest Dataset wiki tree only: page titles, markdown, and parent/subpage
hierarchy. Do not recreate wiki revision history. Warn about attachments, record their
IDs and names, and leave them for manual reattachment; copied markdown links to them
may require repair. Report old-to-new wiki page mappings and flag old Synapse links
in markdown without rewriting them.

The manifest includes a baseline of all source snapshot memberships, labels, comments
and annotations, even when a subset is selected. Generation fails if the source version
list changes while capturing the baseline; releases are built from the captured baseline.
Execution checks that baseline before creating the replacement. Rebuild manifest generation,
previews, and execution refuse existing output files. File and Dataset execution reserve
reports exclusively before downloads or remote writes, and atomically replace them with
flushed progress updates. Do not delete or replace a reserved report while execution runs.
The latest
source Dataset description is copied; other entity-level metadata is not guaranteed.

## DOI policy

DOI minting is separate from Dataset reconstruction and never runs automatically.
Existing DOIs remain attached to the original entities. After a successful rebuild,
consider the separate `mint-dataset-doi` command described in the quick reference. It
defaults to an unversioned latest-Dataset DOI; a snapshot may be explicitly pinned.
The create-or-update endpoint cannot prevent a cross-client race: coordinate writers
and review the production/irreversibility and recovery warnings before execution.

## Safety and validation

- Preview/manifest generation is metadata-only and performs no downloads or Synapse
  mutations.
- `--execute` is required before source bytes are downloaded or replacement entities
  are created.
- Original Files, Datasets, snapshots, and DOIs are never deleted or modified by the
  rebuild workflows.
- Validate rebuilt File histories with `audit-release-staging` before creating a
  Dataset reconstruction manifest.
- Run `audit-dataset-rebuild` against the approved manifest and completed execution report
  before surfacing or retiring any old entity. A renamed or moved replacement fails the
  identity check, and unexpected versions fail the audit. It checks wiki headers by default; use
  `--wiki-markdown` to download and compare markdown. Attachments remain a manual exception.
