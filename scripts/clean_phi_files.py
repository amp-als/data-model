#!/usr/bin/env python3
"""Clean designated PHI/PII columns from every version of files in a Synapse folder.

Step 1 only walks Synapse folder metadata to create an editable column map. It
never downloads or examines file bytes. Step 2 uses the reviewed map to clean
all versions, optionally uploading them as the history of one new File entity.
"""

import argparse
import csv
import json
import os
import shutil
import tempfile
from pathlib import Path

import synapseclient
from synapseclient.models import File


SUPPORTED_SUFFIXES = {'.csv', '.tsv', '.xlsx', '.xlsm'}


def connect(token=None):
    syn = synapseclient.Synapse()
    syn.login(authToken=token or os.getenv('SYNAPSE_AUTH_TOKEN'))
    return syn


def walk_folder_metadata(syn, folder_id):
    """Recursively list file IDs/names using only folder metadata calls."""
    files = {}

    def walk(parent_id, path=''):
        for child in syn.getChildren(parent_id):
            kind = str(child.get('type', '')).lower()
            name = child['name']
            if kind == 'file' or 'fileentity' in kind:
                files[child['id']] = {'name': name, 'path': path}
            elif kind == 'folder' or 'folder' in kind:
                walk(child['id'], f'{path}/{name}' if path else name)

    walk(folder_id)
    return files


def write_column_map(files, output_path, key_kind):
    if key_kind == 'name':
        names = [item['name'] for item in files.values()]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError('Duplicate filenames cannot be map keys; use --map-key id.')
        column_map = {item['name']: [] for item in files.values()}
    else:
        column_map = {syn_id: [] for syn_id in files}
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(column_map, indent=2) + '\n', encoding='utf-8')
    return column_map


def load_and_resolve_column_map(path, files):
    try:
        column_map = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f'Could not read column map {path}: {error}') from error
    if not isinstance(column_map, dict) or not column_map:
        raise ValueError('Column map must be a non-empty JSON object.')

    by_name = {}
    for syn_id, item in files.items():
        by_name.setdefault(item['name'], []).append(syn_id)
    resolved = {}
    for key, columns in column_map.items():
        if not isinstance(key, str) or not isinstance(columns, list) or not all(
            isinstance(column, str) and column for column in columns
        ):
            raise ValueError('Map entries must be "synId-or-filename": ["column", ...].')
        if key in files:
            resolved[key] = columns
        elif key in by_name and len(by_name[key]) == 1:
            resolved[by_name[key][0]] = columns
        elif key in by_name:
            raise ValueError(f'Filename {key!r} occurs more than once; use a Synapse ID.')
        else:
            raise ValueError(f'Column-map key {key!r} is not in the input folder.')
    return resolved


def list_versions(syn, syn_id):
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


def clean_delimited(source, destination, columns):
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
        headers = [header for header in reader.fieldnames if header not in columns]
        with destination.open('w', newline='', encoding='utf-8') as output_file:
            writer_options = {'fieldnames': headers, 'dialect': dialect,
                              'extrasaction': 'ignore'}
            # Sniffer can infer doublequote=False for files containing bare quotes.
            # Normalize output to standard doubled-quote escaping rather than fail.
            writer_options['doublequote'] = True
            writer = csv.DictWriter(output_file, **writer_options)
            writer.writeheader()
            writer.writerows(reader)
    return missing


def clean_workbook(source, destination, columns):
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
    workbook.save(destination)
    return missing


def clean_file(source, destination, columns):
    # Synapse downloads may be extensionless even when the entity name has one.
    # If neither path has an extension, treat the reviewed file as CSV.
    suffix = source.suffix.lower() or destination.suffix.lower() or '.csv'
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f'Unsupported {suffix} file; use CSV, TSV, XLSX, or XLSM.')
    if suffix in {'.csv', '.tsv'}:
        return clean_delimited(source, destination, set(columns))
    return clean_workbook(source, destination, set(columns))


def clean_all_versions(syn, files, column_map, output_dir, upload_folder, merged_name):
    temporary = Path(tempfile.mkdtemp(prefix='clean_phi_files_'))
    output_root = Path(output_dir) if output_dir else temporary / 'cleaned'
    output_root.mkdir(parents=True, exist_ok=True)
    merged_id, cleaned = None, 0
    try:
        for syn_id in sorted(column_map):
            for version in list_versions(syn, syn_id):
                number = version['versionNumber']
                download_dir = temporary / syn_id / f'v{number}'
                download_dir.mkdir(parents=True)
                downloaded = syn.get(syn_id, version=number, downloadLocation=str(download_dir),
                                     downloadFile=True, ifcollision='overwrite.local')
                destination_dir = output_root / syn_id
                destination_dir.mkdir(parents=True, exist_ok=True)
                destination = destination_dir / f'v{number}_{files[syn_id]["name"]}'
                missing = clean_file(Path(downloaded.path), destination, column_map[syn_id])
                if missing:
                    print(f'  ! {syn_id} v{number}: column(s) absent; no removal for them: '
                          f'{", ".join(missing)}')
                print(f'  ✓ {syn_id} v{number} → {destination}')
                cleaned += 1
                if upload_folder:
                    kwargs = {'path': str(destination), 'name': merged_name,
                              'version_label': version.get('versionLabel'),
                              'version_comment': version.get('versionComment')}
                    if merged_id is None:
                        uploaded = File(parent_id=upload_folder, **kwargs).store(synapse_client=syn)
                        merged_id = uploaded.id
                    else:
                        File(id=merged_id, **kwargs).store(synapse_client=syn)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    return cleaned, merged_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', required=True, help='Input Synapse folder (always recursive)')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--write-column-map', metavar='PATH',
                      help='Step 1: metadata-only map scaffold; no file download')
    mode.add_argument('--column-map', metavar='PATH', help='Step 2: reviewed PHI/PII column map')
    parser.add_argument('--map-key', choices=['id', 'name'], default='id')
    parser.add_argument('--output-dir', help='Keep cleaned local files here')
    parser.add_argument('--upload-folder', help='Upload all cleaned versions to one File in this folder')
    parser.add_argument('--merged-name', help='Name of the uploaded merged File')
    parser.add_argument('--execute', action='store_true', help='Required to upload to Synapse')
    parser.add_argument('--auth-token', help='Synapse token (defaults to SYNAPSE_AUTH_TOKEN/default login)')
    args = parser.parse_args()

    if args.column_map and not (args.output_dir or args.upload_folder):
        parser.error('--column-map requires --output-dir or --upload-folder')
    if args.upload_folder and (not args.merged_name or not args.execute):
        parser.error('--upload-folder requires --merged-name and --execute')

    syn = connect(args.auth_token)
    files = walk_folder_metadata(syn, args.folder)
    if not files:
        parser.error('No files found in the input folder')
    if args.write_column_map:
        column_map = write_column_map(files, args.write_column_map, args.map_key)
        print(f'Wrote {len(column_map)} editable keys to {args.write_column_map}')
        print('No file bytes were downloaded or inspected.')
        return

    column_map = load_and_resolve_column_map(args.column_map, files)
    cleaned, merged_id = clean_all_versions(
        syn, files, column_map, args.output_dir, args.upload_folder, args.merged_name,
    )
    print(f'Cleaned {cleaned} version(s).')
    if merged_id:
        print(f'Created merged Synapse File: {merged_id}')


if __name__ == '__main__':
    main()
