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
from ruamel.yaml import YAML

# --- Helper Functions ---

def to_camel_case(snake_str):
    """Converts snake_case to camelCase."""
    if not snake_str:
        return ""
    components = snake_str.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])

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

def parse_view_to_class_mapping(file_path):
    """Parses the view_to_class_mapping.md file."""
    mapping = {}
    try:
        with open(file_path, 'r') as f:
            for line in f:
                match = re.search(r'\|\s*`?(v_ALLALS_(?:PR|AS)_([A-Z0-9_]+))`?\s*\|\s*`?([^`|]+)`?', line)
                if match:
                    view_name = match.group(1).strip()
                    class_name = match.group(3).split('(')[0].strip()
                    if view_name and class_name:
                        mapping[view_name] = class_name
    except IOError as e:
        print(f"Error reading mapping file {file_path}: {e}", file=sys.stderr)
    return mapping

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
    parser.add_argument("--dd-dir", required=True, help="Path to the root data dictionary directory.")
    parser.add_argument("--view-to-class", required=True, help="Path to the view_to_class_mapping.md file.")
    parser.add_argument("--dry-run", action="store_true", help="If set, the script will not write any files.")
    
    args = parser.parse_args()

    # --- Load Data ---
    print("Loading data...")
    view_to_class = parse_view_to_class_mapping(args.view_to_class)
    
    all_dd_data = {}
    for dataset in ["ASSESS", "PREVENT"]:
        dd_path = os.path.join(args.dd_dir, dataset, f"{dataset}_DATA_DICTIONARY_OCTOBER_28.csv")
        all_dd_data.update(parse_data_dictionary(dd_path))

    yaml_files = load_yaml_files(args.modules_dir)
    
    # --- Process Data ---
    print("Processing data model updates...")
    for view_name, dd_fields in all_dd_data.items():
        if view_name not in view_to_class:
            print(f"Warning: View '{view_name}' not found in mapping file. Skipping.", file=sys.stderr)
            continue
            
        class_name = view_to_class[view_name]
        
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
            yaml_files[target_file] = {'classes': {class_name: {'is_a': 'ClinicalAssessment', 'attributes': {}}}}

        
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
