#!/usr/bin/env python
# coding: utf-8

"""
This script updates the data model from the data dictionaries.
"""

import csv
import json
import os
import re
import sys
import argparse
import subprocess
from ruamel.yaml import YAML

# --- Helper Functions ---

def to_camel_case(snake_str):
    """Converts snake_case to camelCase."""
    if not snake_str:
        return ""
    components = snake_str.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])

def descriptive_to_class_name(desc_str):
    """Converts a descriptive string to a PascalCase class name."""
    # Remove content in parentheses and other special characters
    s = re.sub(r'\(.*\)', '', desc_str).strip()
    s = re.sub(r'[^A-Za-z0-9\s]', '', s)
    # Capitalize each word and join
    return ''.join(word.capitalize() for word in s.split())

def parse_data_dictionary(file_path):
    """Parses a data dictionary CSV file."""
    data = {}
    current_view = None
    try:
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            next(reader) # Skip header
            for row in reader:
                if not row or not any(row):
                    continue
                view_name = row[0]
                if view_name:
                    current_view = view_name
                    if current_view not in data:
                        data[current_view] = []
                
                if current_view and len(row) > 1 and row[1]:
                    field_info = {
                        'field': row[1],
                        'description': row[2] if len(row) > 2 else "",
                        'values': row[3] if len(row) > 3 else ""
                    }
                    data[current_view].append(field_info)
    except (IOError, StopIteration) as e:
        print(f"Error reading data dictionary {file_path}: {e}", file=sys.stderr)
    return data

def load_yaml_files(modules_dir):
    """Loads all YAML files from the modules directory."""
    yaml_data = {}
    yaml = YAML()
    for root, _, files in os.walk(modules_dir):
        for file in files:
            if file.endswith(".yaml") or file.endswith(".yml"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r') as f:
                        yaml_data[file_path] = yaml.load(f)
                except Exception as e:
                    print(f"Error loading YAML file {file_path}: {e}", file=sys.stderr)
    return yaml_data

# --- Main Logic ---

def main():
    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(description="Update data model from data dictionaries.")
    parser.add_argument("--modules-dir", required=True, help="Path to the modules directory.")
    parser.add_argument("--dataset-files-dir", required=True, help="Path to the directory containing the dataset files for form name mapping.")
    parser.add_argument("--dd-files", nargs='+', required=True, help="One or more paths to the data dictionary CSV files.")
    parser.add_argument("--dry-run", action="store_true", help="If set, the script will not write any files.")
    
    args = parser.parse_args()

    # --- Refresh mappings and load data ---
    print("Refreshing form name mappings...")
    subprocess.run([
        "/home/ramayyala/.local/bin/micromamba", "run", "-n", "amp-als",
        "python", "scripts/model_management/ALL_ALS/get_form_names.py", args.dataset_files_dir
    ], check=True)
    print("Form name mappings refreshed.")

    print("Loading data...")
    with open("mapping/ALL_ALS/form_name_mappings.json", 'r') as f:
        form_name_mappings = json.load(f)
    
    all_dd_data = {}
    for dd_file_path in args.dd_files:
        all_dd_data.update(parse_data_dictionary(dd_file_path))

    yaml_files = load_yaml_files(args.modules_dir)
    
    # --- Process Data ---
    print("Processing data model updates...")
    for view_name, dd_fields in all_dd_data.items():
        
        match = re.search(r'v_ALLALS_(?:PR|AS)_([A-Z0-9_]+)', view_name)
        if not match:
            print(f"Warning: Could not parse view name '{view_name}'. Skipping.", file=sys.stderr)
            continue
        short_name = match.group(1)

        descriptive_name = form_name_mappings.get(short_name)
        if not descriptive_name or "FILE IS EMPTY" in descriptive_name:
            print(f"Warning: No valid descriptive name for short name '{short_name}'. Skipping view '{view_name}'.", file=sys.stderr)
            continue
        
        class_name = descriptive_to_class_name(descriptive_name)
        
        target_file = None
        class_found = False
        for path, data in yaml_files.items():
            if data and 'classes' in data and class_name in data['classes']:
                target_file = path
                class_found = True
                break

        if not class_found:
            new_file_path = os.path.join(args.modules_dir, "clinical", "assessments", f"{class_name.lower().replace(' ', '_')}.yaml")
            print(f"Creating new class '{class_name}' in file '{new_file_path}'")
            target_file = new_file_path
            
            yaml_files[target_file] = {'classes': {class_name: {
                'is_a': 'ClinicalAssessment',
                'title': descriptive_name,
                'attributes': {}
            }}}

        
        class_def = yaml_files[target_file]['classes'][class_name]
        if 'attributes' not in class_def or class_def['attributes'] is None:
            class_def['attributes'] = {}

        for field in dd_fields:
            attr_name = to_camel_case(field['field'])
            if attr_name and attr_name not in class_def['attributes']:
                print(f"  Adding attribute '{attr_name}' to class '{class_name}'")
                
                class_def['attributes'][attr_name] = {
                    'title': field['description'],
                    'description': "[DESCRIPTION TO BE GENERATED]",
                    'range': 'string' # Default range
                }

    # --- Write Changes ---
    if not args.dry_run:
        print("Writing changes to YAML files...")
        yaml = YAML()
        yaml.indent(mapping=2, sequence=4, offset=2)
        for path, data in yaml_files.items():
            try:
                # Create directory if it doesn't exist
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'w') as f:
                    yaml.dump(data, f)
            except Exception as e:
                print(f"Error writing to {path}: {e}", file=sys.stderr)
    else:
        print("Dry run complete. No files were written.")


if __name__ == "__main__":
    main()
