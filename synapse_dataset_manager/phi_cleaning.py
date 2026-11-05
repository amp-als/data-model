"""Metadata-first PHI/PII column removal for versioned Synapse files."""

import csv
import json
import shutil
import tempfile
from pathlib import Path

from synapseclient.models import File


SUPPORTED_SUFFIXES = {'.csv', '.tsv', '.xlsx', '.xlsm'}


def walk_folder_metadata(syn, folder_id):
    """Return recursively discovered files without fetching entities or bytes."""
    files = {}

    def walk(parent_id, path=''):
        for child in syn.getChildren(parent_id):
            kind = str(child.get('type', '')).lower()
            name = child['name']
            child_path = f'{path}/{name}' if path else name
            if kind == 'file' or 'fileentity' in kind:
                files[child['id']] = {'name': name, 'path': path}
            elif kind == 'folder' or 'folder' in kind:
                walk(child['id'], child_path)

    walk(folder_id)
    return files


def write_column_map(files, output_path, key_kind='id'):
    """Write an editable ``{synId|filename: []}`` column-removal map."""
    if key_kind == 'name':
        names = [item['name'] for item in files.values()]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(
                'Cannot use filenames as map keys because they are not unique: '
                + ', '.join(duplicates[:5]) + '. Use --map-key id instead.'
            )
        result = {item['name']: [] for item in files.values()}
    else:
        result = {syn_id: [] for syn_id in files}
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def load_column_map(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f'Could not read column map {path}: {error}') from error
    if not isinstance(value, dict) or not value:
        raise ValueError('Column map must be a non-empty JSON object.')
    for key, columns in value.items():
        if not isinstance(key, str) or not isinstance(columns, list) or not all(
            isinstance(column, str) and column for column in columns
        ):
            raise ValueError('Each column-map entry must be "synId-or-filename": ["column", ...].')
    return value


def resolve_column_map(column_map, files):
    """Resolve IDs or unique filenames in an editable map to Synapse IDs."""
    by_name = {}
    for syn_id, item in files.items():
        by_name.setdefault(item['name'], []).append(syn_id)
    resolved = {}
    for key, columns in column_map.items():
        if key in files:
            resolved[key] = columns
        elif key in by_name and len(by_name[key]) == 1:
            resolved[by_name[key][0]] = columns
        elif key in by_name:
            raise ValueError(f'Filename {key!r} occurs more than once; use its Synapse ID as the map key.')
        else:
            raise ValueError(f'Column-map key {key!r} was not found in the input folder.')
    return resolved


def list_versions(syn, syn_id):
    """List version metadata only; this endpoint never fetches file bytes."""
    versions, offset = [], 0
    while True:
        page = syn.restGET(f'/entity/{syn_id}/version?offset={offset}&limit=100')
        batch = page.get('results', page) if isinstance(page, dict) else page
        if not batch:
            break
        versions.extend(batch)
        if len(batch) < 100:
            break
        offset += len(batch)
    return sorted(versions, key=lambda item: item['versionNumber'])


def _clean_delimited(source, destination, columns):
    with source.open('r', newline='', encoding='utf-8-sig') as input_file:
        sample = input_file.read(8192)
        input_file.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=',\t;|')
        except csv.Error:
            dialect = csv.excel_tab if source.suffix.lower() == '.tsv' else csv.excel
        reader = csv.DictReader(input_file, dialect=dialect)
        if not reader.fieldnames:
            raise ValueError(f'{source.name} has no header row.')
        missing = sorted(set(columns) - set(reader.fieldnames))
        if missing:
            raise ValueError(f'{source.name}: designated column(s) not found: {", ".join(missing)}')
        retained = [name for name in reader.fieldnames if name not in columns]
        with destination.open('w', newline='', encoding='utf-8') as output_file:
            writer = csv.DictWriter(output_file, fieldnames=retained, dialect=dialect,
                                    extrasaction='ignore')
            writer.writeheader()
            writer.writerows(reader)


def _clean_workbook(source, destination, columns):
    try:
        import openpyxl
    except ImportError as error:
        raise ValueError('openpyxl is required to clean Excel files.') from error
    workbook = openpyxl.load_workbook(source)
    found = set()
    for sheet in workbook.worksheets:
        headers = [cell.value for cell in sheet[1]]
        indexes = [index + 1 for index, header in enumerate(headers) if header in columns]
        found.update(headers[index - 1] for index in indexes)
        for index in reversed(indexes):
            sheet.delete_cols(index)
    missing = sorted(set(columns) - found)
    if missing:
        raise ValueError(f'{source.name}: designated column(s) not found: {", ".join(missing)}')
    workbook.save(destination)


def clean_file(source, destination, columns):
    """Remove exact header names from a supported tabular file."""
    suffix = source.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f'Unsupported file type {suffix or "(none)"}; supported: CSV, TSV, XLSX, XLSM.')
    if suffix in {'.csv', '.tsv'}:
        _clean_delimited(source, destination, set(columns))
    else:
        _clean_workbook(source, destination, set(columns))


def process_phi_files(syn, folder_id, column_map, output_dir, upload_folder=None,
                      merged_name=None, execute=False):
    """Download every selected version, clean it, and optionally version one output File."""
    files = walk_folder_metadata(syn, folder_id)
    resolved = resolve_column_map(column_map, files)
    if not resolved:
        raise ValueError('No files were selected by the column map.')
    if upload_folder and not execute:
        raise ValueError('--upload-folder requires --execute; cleaned local files are still written.')
    if upload_folder and not merged_name:
        raise ValueError('--merged-name is required with --upload-folder.')

    temp_root = Path(tempfile.mkdtemp(prefix='sdm_phi_clean_'))
    # Upload-only mode retains cleaned bytes only long enough to store them.
    output_root = Path(output_dir) if output_dir else temp_root / 'cleaned'
    output_root.mkdir(parents=True, exist_ok=True)
    merged_id = None
    completed = 0
    try:
        for syn_id in sorted(resolved):
            columns = resolved[syn_id]
            versions = list_versions(syn, syn_id)
            if not versions:
                raise ValueError(f'{syn_id} has no versions.')
            for version in versions:
                number = version['versionNumber']
                download_dir = temp_root / syn_id / f'v{number}'
                download_dir.mkdir(parents=True)
                entity = syn.get(syn_id, version=number, downloadLocation=str(download_dir),
                                 downloadFile=True, ifcollision='overwrite.local')
                source = Path(entity.path)
                destination_dir = output_root / syn_id
                destination_dir.mkdir(parents=True, exist_ok=True)
                destination = destination_dir / f'v{number}_{files[syn_id]["name"]}'
                clean_file(source, destination, columns)
                print(f'  ✓ {syn_id} v{number} → {destination}')
                completed += 1

                if upload_folder:
                    label = version.get('versionLabel')
                    comment = version.get('versionComment')
                    if merged_id is None:
                        uploaded = File(path=str(destination), parent_id=upload_folder,
                                        name=merged_name, version_label=label,
                                        version_comment=comment).store(synapse_client=syn)
                        merged_id = uploaded.id
                    else:
                        File(id=merged_id, path=str(destination), name=merged_name,
                             version_label=label, version_comment=comment).store(synapse_client=syn)
        if not completed:
            raise ValueError('No versions were cleaned. Add columns to at least one map entry.')
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
    return completed, merged_id
