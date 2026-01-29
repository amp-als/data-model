#!/usr/bin/env python3
"""
Synapse Dataset Manager - Unified SOP Script

This script provides a generalized workflow for managing Synapse datasets:
- MODE 1: CREATE - Create new datasets from scratch (like Trehalose workflow)
- MODE 2: UPDATE - Update existing datasets with new versions (like ALL-ALS SOP)

Author: Converted from Jupyter notebooks
"""

import os
import sys
import csv
import json
import shutil
import re
import argparse
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set, Union
from collections import defaultdict, Counter

# Third-party imports
import yaml
import synapseclient
from synapseclient.models import (
    File, Folder, Project, Table, EntityView, Dataset,
    DatasetCollection, Column, ColumnType, FacetType, EntityRef, ViewTypeMask
)
from synapseclient import Wiki
from jsonschema import validate, ValidationError, Draft7Validator


# ==================== CONFIGURATION ====================

def load_config_file(config_path="config.yaml"):
    """Load configuration from YAML file"""
    if not os.path.exists(config_path):
        return {}

    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f) or {}
        print(f"✓ Loaded config from {config_path}")
        return config
    except Exception as e:
        print(f"⚠️  Warning: Could not load {config_path}: {e}")
        return {}


class Config:
    """Configuration for dataset management workflows"""

    def __init__(self, config_file=None):
        # Load from config file first
        file_config = {}
        if config_file:
            file_config = load_config_file(config_file)
        elif os.path.exists("config.yaml"):
            file_config = load_config_file("config.yaml")

        # Synapse Authentication (env var > config file)
        synapse_config = file_config.get('synapse', {})
        self.SYNAPSE_AUTH_TOKEN = os.getenv("SYNAPSE_AUTH_TOKEN") or synapse_config.get('auth_token', "")
        self.SYNAPSE_PROJECT_ID = os.getenv("SYNAPSE_PROJECT_ID") or synapse_config.get('project_id', "syn68702804")
        self.DATASETS_COLLECTION_ID = os.getenv("DATASETS_COLLECTION_ID") or synapse_config.get('datasets_collection_id', "syn66496326")

        # Directories (env var > config file > defaults)
        dir_config = file_config.get('directories', {})
        self.BASE_DIR = os.getenv("BASE_DIR") or dir_config.get('base_dir', os.getcwd())
        self.SCHEMA_BASE_PATH = os.path.join(
            self.BASE_DIR,
            dir_config.get('schema_path', 'json-schemas').lstrip('./')
        )
        self.ANNOTATIONS_DIR = os.path.join(
            self.BASE_DIR,
            dir_config.get('annotations_dir', 'annotations').lstrip('./')
        )
        os.makedirs(self.ANNOTATIONS_DIR, exist_ok=True)

        # Workflow control (env var > config file > defaults)
        workflow_config = file_config.get('workflow', {})
        self.DRY_RUN = self._parse_bool(
            os.getenv("DRY_RUN") or workflow_config.get('dry_run', True)
        )
        self.VERBOSE = self._parse_bool(
            os.getenv("VERBOSE") or workflow_config.get('verbose', True)
        )
        self.USE_AI = self._parse_bool(
            os.getenv("USE_AI") or workflow_config.get('use_ai', True)
        )

        # AI Settings
        ai_config = file_config.get('ai', {})
        self.AI_ENABLED = ai_config.get('enabled', True)
        self.AI_TIMEOUT = int(ai_config.get('timeout', 60))
        self.AI_MODEL = ai_config.get('model', 'gemini-1.5-flash')
        self.AI_MAX_LINES = int(ai_config.get('max_file_lines', 100))

        # Store full config for dataset-specific access
        self.full_config = file_config

    def _parse_bool(self, value):
        """Parse boolean from various formats"""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "y")
        return bool(value)

    def get_dataset_config(self, dataset_name):
        """Get dataset-specific configuration"""
        datasets = self.full_config.get('datasets', {})
        return datasets.get(dataset_name, {})

    def validate(self):
        """Validate configuration"""
        print("Configuration Validation:")
        print("-" * 50)

        if not self.SYNAPSE_AUTH_TOKEN:
            print("⚠️  WARNING: SYNAPSE_AUTH_TOKEN not set")
            print("   Set in config.yaml or use environment variable")
        if not self.SYNAPSE_PROJECT_ID:
            print("⚠️  WARNING: SYNAPSE_PROJECT_ID not set")

        print(f"✓ Base directory: {self.BASE_DIR}")
        print(f"✓ Schema path: {self.SCHEMA_BASE_PATH}")
        print(f"✓ Annotations directory: {self.ANNOTATIONS_DIR}")
        print(f"✓ DRY_RUN mode: {self.DRY_RUN}")
        print(f"✓ AI enabled: {self.AI_ENABLED}")
        print("-" * 50)


# ==================== SYNAPSE CONNECTION ====================

def connect_to_synapse(config):
    """
    Connect to Synapse using configured credentials or default discovery.

    Priority:
    1. SYNAPSE_AUTH_TOKEN environment variable
    2. auth_token in config.yaml
    3. Synapse default credential discovery (~/.synapseConfig)
    """
    try:
        syn = synapseclient.Synapse()

        # If token is explicitly provided (env var or config), use it
        if config.SYNAPSE_AUTH_TOKEN:
            syn.login(authToken=config.SYNAPSE_AUTH_TOKEN)
            print("✓ Connected to Synapse (using explicit token)")
        else:
            # Use Synapse's default credential discovery
            # This checks ~/.synapseConfig automatically
            syn.login()
            print("✓ Connected to Synapse (using default credentials)")

        return syn
    except Exception as e:
        print(f"✗ Failed to connect to Synapse: {e}")
        print("\nAuthentication options:")
        print("  1. Set SYNAPSE_AUTH_TOKEN environment variable")
        print("  2. Add auth_token to config.yaml")
        print("  3. Run 'synapse login' to configure ~/.synapseConfig")
        raise


# ==================== SCHEMA LOADING ====================

def get_json_schema_path(base_path, schema_name):
    """Get the path to a JSON schema file"""
    json_schema_file = os.path.join(base_path, f"{schema_name}.json")
    if os.path.exists(json_schema_file):
        return json_schema_file
    return None


def load_json_schema(schema_path):
    """Load a JSON schema from file"""
    try:
        with open(schema_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Could not load schema {schema_path}: {e}")
        return None


def get_all_schemas(schema_base_path, verbose=False):
    """
    Load all JSON schema files from json-schemas directory.
    Returns: {schema_name: schema_dict}
    """
    # Look for json-schemas directory
    json_schema_dir = os.path.join(os.path.dirname(schema_base_path), "json-schemas")

    if not os.path.exists(json_schema_dir):
        # Fallback to modules directory if json-schemas doesn't exist
        json_schema_dir = schema_base_path
        print(f"⚠️  json-schemas directory not found, using {schema_base_path}")

    schemas = {}

    # Load all .json files
    for json_file in Path(json_schema_dir).glob("*.json"):
        schema_name = json_file.stem  # Filename without .json
        try:
            with open(json_file, 'r') as f:
                schema_data = json.load(f)
                schemas[schema_name] = schema_data
                if verbose:
                    print(f"  Loaded {schema_name}.json")
        except Exception as e:
            if verbose:
                print(f"  ⚠️  Could not load {json_file}: {e}")

    print(f"✓ Loaded {len(schemas)} JSON schemas")
    return schemas


def get_schema_for_type(file_type, all_schemas):
    """
    Get the JSON schema for a given file/dataset type.

    Args:
        file_type: Type name (e.g., 'ClinicalFile', 'OmicFile', 'ClinicalDataset')
        all_schemas: Dictionary of loaded schemas

    Returns:
        JSON schema dict or None
    """
    # Try exact match first
    if file_type in all_schemas:
        return all_schemas[file_type]

    # Try common variations
    variations = [
        file_type,
        file_type.replace('File', ''),
        file_type.replace('Dataset', ''),
        f"{file_type}File",
        f"{file_type}Dataset"
    ]

    for variation in variations:
        if variation in all_schemas:
            return all_schemas[variation]

    return None


def get_required_fields(schema):
    """Extract required fields from JSON schema"""
    if not schema:
        return []
    return schema.get('required', [])


def get_field_info(schema):
    """
    Extract field information from JSON schema for template generation.
    Returns: {field_name: {'type': ..., 'enum': ..., 'description': ...}}
    """
    if not schema or 'properties' not in schema:
        return {}

    field_info = {}
    properties = schema.get('properties', {})

    for field_name, field_def in properties.items():
        info = {
            'type': field_def.get('type', 'string'),
            'description': field_def.get('description', ''),
            'enum': field_def.get('enum', [])
        }

        # Check if it's an array type
        if info['type'] == 'array':
            items = field_def.get('items', {})
            info['item_type'] = items.get('type', 'string')
            info['item_enum'] = items.get('enum', [])

        field_info[field_name] = info

    return field_info


# ==================== FILE TYPE DETECTION ====================

def detect_file_type(filename, file_path=None, all_schemas=None, dataset_config=None):
    """
    Detect file type based on dataset config or filename patterns.

    Priority:
    1. dataset_config['dataset_type'] if defined ('Clinical' or 'Omic')
    2. Pattern matching on filename
    3. Default to base 'File' schema

    Returns: Schema class name (e.g., 'ClinicalFile', 'OmicFile', 'File')
    """
    # Check if dataset type is explicitly defined in config
    if dataset_config and 'dataset_type' in dataset_config:
        dataset_type = dataset_config['dataset_type']
        if dataset_type == 'Clinical':
            return 'ClinicalFile'
        elif dataset_type == 'Omic':
            return 'OmicFile'

    # Fall back to pattern matching
    filename_lower = filename.lower()

    # Clinical data patterns
    clinical_patterns = [
        'clinical', 'demog', 'demographics', 'patient', 'subject',
        'medical', 'history', 'assessment', 'visit'
    ]

    # Omic data patterns
    omic_patterns = [
        'rna', 'dna', 'protein', 'metabol', 'proteom', 'genom',
        'transcriptom', 'seq', 'soma', 'olink', 'assay'
    ]

    # Check for omic patterns
    if any(pattern in filename_lower for pattern in omic_patterns):
        return 'OmicFile'

    # Check for clinical patterns
    if any(pattern in filename_lower for pattern in clinical_patterns):
        return 'ClinicalFile'

    # Default to base File schema if pattern matching fails
    return 'File'


def detect_dataset_type(dataset_name, staging_folder_name=None, dataset_config=None):
    """
    Detect dataset type based on config or name patterns.

    Priority:
    1. dataset_config['dataset_type'] if defined ('Clinical' or 'Omic')
    2. Pattern matching on dataset name
    3. Default to base 'Dataset' schema

    Returns: Schema class name (e.g., 'ClinicalDataset', 'OmicDataset', 'Dataset')
    """
    # Check if dataset type is explicitly defined in config
    if dataset_config and 'dataset_type' in dataset_config:
        dataset_type = dataset_config['dataset_type']
        if dataset_type == 'Clinical':
            return 'ClinicalDataset'
        elif dataset_type == 'Omic':
            return 'OmicDataset'

    # Fall back to pattern matching
    name_lower = dataset_name.lower()

    omic_patterns = ['omic', 'rna', 'dna', 'protein', 'metabol', 'proteom']

    if any(pattern in name_lower for pattern in omic_patterns):
        return 'OmicDataset'

    clinical_patterns = ['clinical', 'demog', 'patient', 'subject', 'medical', 'assessment']

    if any(pattern in name_lower for pattern in clinical_patterns):
        return 'ClinicalDataset'

    # Default to base Dataset schema if pattern matching fails
    return 'Dataset'


# ==================== ANNOTATION HANDLING ====================

def clean_annotations_for_synapse(annotation):
    """Remove metadata fields and empty values before applying to Synapse"""
    cleaned = {}

    for key, value in annotation.items():
        if key.startswith('_'):
            continue

        if hasattr(value, '__class__') and value.__class__.__name__ == 'File':
            value = value.id if hasattr(value, 'id') else str(value)
        elif isinstance(value, list):
            cleaned_list = []
            for item in value:
                if hasattr(item, '__class__') and item.__class__.__name__ == 'File':
                    cleaned_list.append(item.id if hasattr(item, 'id') else str(item))
                else:
                    cleaned_list.append(item)
            value = cleaned_list

        if value is None:
            continue
        if isinstance(value, str) and value == "":
            continue
        if isinstance(value, list) and (len(value) == 0 or (len(value) == 1 and value[0] == "")):
            continue

        cleaned[key] = value

    return cleaned


def validate_annotation_against_schema(annotation, file_type, all_schemas):
    """
    Validate a single annotation against its JSON schema.

    Args:
        annotation: Dict of annotations to validate
        file_type: Type name (e.g., 'ClinicalFile', 'OmicDataset')
        all_schemas: Dict of loaded JSON schemas

    Returns:
        (is_valid, errors, warnings)
    """
    errors = []
    warnings = []

    # Get the schema for this type
    schema = get_schema_for_type(file_type, all_schemas)

    if not schema:
        errors.append(f"Schema not found for file type: {file_type}")
        return False, errors, warnings

    # Clean annotation (remove metadata fields for validation)
    clean_annot = {k: v for k, v in annotation.items() if not k.startswith('_')}

    # Use jsonschema library for proper validation
    try:
        # Create validator
        validator = Draft7Validator(schema)

        # Collect all validation errors
        validation_errors = list(validator.iter_errors(clean_annot))

        for error in validation_errors:
            # Format error message
            field_path = '.'.join(str(p) for p in error.path) if error.path else 'root'
            error_msg = f"{field_path}: {error.message}"
            errors.append(error_msg)

    except Exception as e:
        errors.append(f"Validation error: {e}")

    # Additional checks and warnings
    required_fields = get_required_fields(schema)

    for field in required_fields:
        if field not in clean_annot:
            errors.append(f"Required field missing: {field}")
        elif clean_annot[field] in ["", [""], [], None]:
            errors.append(f"Required field empty: {field}")

    # Check if any fields are filled
    filled_fields = sum(1 for k, v in clean_annot.items()
                       if v not in ["", [""], [], None])

    if filled_fields == 0:
        warnings.append("No annotation fields are filled")

    # Check for unknown fields (not in schema)
    schema_properties = schema.get('properties', {})
    for field_name in clean_annot.keys():
        if field_name not in schema_properties:
            warnings.append(f"Field '{field_name}' not in schema (will be ignored)")

    is_valid = len(errors) == 0
    return is_valid, errors, warnings


def create_annotation_template(all_schemas, file_type='ClinicalFile'):
    """
    Generate empty annotation template from JSON schema.

    Args:
        all_schemas: Dict of loaded JSON schemas
        file_type: Type name (e.g., 'ClinicalFile', 'OmicDataset')

    Returns:
        Template dict with empty values
    """
    schema = get_schema_for_type(file_type, all_schemas)

    if not schema:
        print(f"⚠️  Schema not found for {file_type}, using empty template")
        return {
            '_file_type': file_type,
            '_schema_source': 'data-model',
            '_created_timestamp': datetime.now().isoformat()
        }

    template = {}
    field_info = get_field_info(schema)

    for field_name, info in field_info.items():
        # Create empty value based on type
        if info['type'] == 'array':
            template[field_name] = ['']
        elif info['type'] == 'boolean':
            template[field_name] = False
        elif info['type'] == 'integer' or info['type'] == 'number':
            template[field_name] = None
        else:
            template[field_name] = ''

    # Add metadata fields
    template['_file_type'] = file_type
    template['_schema_source'] = 'json-schema'
    template['_created_timestamp'] = datetime.now().isoformat()

    return template


def merge_annotations_smartly(existing, template):
    """
    Smart merge: Keep existing values, add new fields from template.
    Used for CREATE workflow.
    """
    merged = template.copy()

    for key, value in existing.items():
        if value not in ["", [""], [], None]:
            merged[key] = value

    return merged


def merge_file_annotations_priority(old_annot, new_annot, template):
    """
    Priority merge: old (release) > new (staging) > template.
    Used for UPDATE workflow.
    """
    merged = {}
    merged.update(template)

    for key, value in new_annot.items():
        if value not in ["", [""], [], None]:
            merged[key] = value

    for key, value in old_annot.items():
        if value not in ["", [""], [], None]:
            merged[key] = value

    return merged


# ==================== CREATE WORKFLOW FUNCTIONS ====================

def enumerate_files_with_folders(syn, folder_id, recursive=True, verbose=False):
    """
    Enumerate files in a Synapse folder recursively.
    Returns: {syn_id: {'name': filename, 'path': folder_path, 'annotations': {}}}
    """
    print(f"Enumerating files from folder {folder_id}...")

    files_dict = {}
    total_items = 0

    def _process_folder(folder_syn_id, path_prefix=""):
        """Recursively process folder"""
        nonlocal total_items
        try:
            children = list(syn.getChildren(folder_syn_id))
            total_items += len(children)

            if verbose:
                print(f"  Checking folder {folder_syn_id}: {len(children)} items")

            for child in children:
                child_id = child['id']
                child_name = child['name']
                child_type = child.get('type', '')

                if verbose:
                    print(f"    Item: {child_name} (type: {child_type})")

                # Check for file types - handle both old and new API
                # Types: 'file', 'org.sagebionetworks.repo.model.FileEntity'
                if child_type.lower() == 'file' or 'fileentity' in child_type.lower():
                    try:
                        entity = syn.get(child_id, downloadFile=False)
                        annotations = dict(entity.annotations) if hasattr(entity, 'annotations') else {}

                        files_dict[child_id] = {
                            'name': child_name,
                            'path': path_prefix,
                            'annotations': annotations
                        }

                        if verbose:
                            print(f"      ✓ Added file: {path_prefix}/{child_name}")
                    except Exception as e:
                        print(f"      ⚠️  Error processing file {child_name}: {e}")

                # Check for folder types - handle both old and new API
                # Types: 'folder', 'org.sagebionetworks.repo.model.Folder'
                elif (child_type.lower() == 'folder' or 'folder' in child_type.lower()) and recursive:
                    new_path = f"{path_prefix}/{child_name}" if path_prefix else child_name
                    if verbose:
                        print(f"      → Entering subfolder: {child_name}")
                    _process_folder(child_id, new_path)
                else:
                    if verbose:
                        print(f"      ⊘ Skipped (type: {child_type})")

        except Exception as e:
            print(f"  ✗ Error processing folder {folder_syn_id}: {e}")
            import traceback
            traceback.print_exc()

    _process_folder(folder_id)
    print(f"✓ Found {len(files_dict)} files (from {total_items} total items)")

    if len(files_dict) == 0 and total_items > 0:
        print("⚠️  WARNING: Items found but no files detected.")
        print("   This might mean:")
        print("   - Files are in subfolders (use recursive=True)")
        print("   - Files are a different entity type")
        print("   - Permission issues")
        print(f"   Run with --verbose to see item types")

    return files_dict


def apply_annotations_to_files(syn, file_annotations_dict, dry_run=True, verbose=False):
    """
    Apply annotations to file entities in Synapse.
    Used in CREATE workflow.
    """
    success_count = 0
    error_count = 0

    for syn_id, file_data in file_annotations_dict.items():
        filename = list(file_data.keys())[0]
        annotations = file_data[filename]

        try:
            cleaned = clean_annotations_for_synapse(annotations)

            if dry_run:
                print(f"  [DRY_RUN] Would apply {len(cleaned)} annotations to {filename}")
                success_count += 1
            else:
                entity = syn.get(syn_id, downloadFile=False)
                entity.annotations = cleaned
                syn.store(entity, forceVersion=False)

                if verbose:
                    print(f"  ✓ Applied annotations to {filename}")
                success_count += 1

        except Exception as e:
            print(f"  ✗ Error applying annotations to {filename}: {e}")
            error_count += 1

    return success_count, error_count


def create_dataset_entity(syn, dataset_name, dataset_annotations, project_id,
                         all_schemas, dry_run=True):
    """
    Create a new Dataset entity in Synapse.
    Returns: dataset_syn_id or None
    """
    try:
        # Remove file-level fields that shouldn't be in dataset annotations
        file_level_fields = {
            'assay', 'platform', 'specimenType', 'cellType', 'libraryLayout',
            'FACSPopulation', 'GEOSuperSeries', 'biospecimenType', 'originalSampleName',
            'fileFormat', 'sex', 'age', 'diagnosis', 'tissueType', 'tissueOrigin'
        }

        # Clean dataset annotations
        cleaned_dataset_annotations = {}
        for key, value in dataset_annotations.items():
            if key not in file_level_fields:
                # Remove empty string arrays
                if isinstance(value, list) and value == ['']:
                    cleaned_dataset_annotations[key] = []
                else:
                    cleaned_dataset_annotations[key] = value

        # Validate dataset annotations (warnings only - main validation already done in STEP 1)
        dataset_type = cleaned_dataset_annotations.get('_dataset_type', 'ClinicalDataset')
        is_valid, errors, warnings = validate_annotation_against_schema(
            cleaned_dataset_annotations, dataset_type, all_schemas
        )

        if not is_valid:
            print(f"  ⚠️  Dataset has validation warnings (proceeding as approved in STEP 1):")
            for error in errors[:3]:  # Show first 3 errors only
                print(f"    - {error}")
            if len(errors) > 3:
                print(f"    ... and {len(errors) - 3} more")

        cleaned = clean_annotations_for_synapse(cleaned_dataset_annotations)

        if dry_run:
            print(f"  [DRY_RUN] Would create dataset '{dataset_name}' with {len(cleaned)} annotations")
            return "syn_DRYRUN_DATASET"

        # Create dataset
        dataset = Dataset(
            name=dataset_name,
            parent_id=project_id,
            annotations=cleaned
        )
        dataset = dataset.store()

        print(f"  ✓ Created dataset: {dataset.id}")
        return dataset.id

    except Exception as e:
        print(f"  ✗ Error creating dataset: {e}")
        return None


def add_files_to_dataset(syn, dataset_id, file_syn_ids, dry_run=True):
    """Add files to a dataset"""
    try:
        if dry_run:
            print(f"  [DRY_RUN] Would add {len(file_syn_ids)} files to dataset {dataset_id}")
            return True

        dataset = Dataset(dataset_id).get()

        for file_id in file_syn_ids:
            file_ref = File(id=file_id)
            dataset.add_item(file_ref)

        dataset.store()
        print(f"  ✓ Added {len(file_syn_ids)} files to dataset")
        return True

    except Exception as e:
        print(f"  ✗ Error adding files to dataset: {e}")
        return False


def add_dataset_columns(syn, dataset_id, all_schemas, file_type='ClinicalFile', dry_run=True):
    """Add annotation columns to dataset for faceted search"""
    try:
        # Get schema and field info
        schema = get_schema_for_type(file_type, all_schemas)
        if not schema:
            print(f"  ⚠️  Schema not found for {file_type}, skipping column addition")
            return False

        field_info = get_field_info(schema)

        # Count fields with enums
        enum_fields = {name: info for name, info in field_info.items()
                      if info.get('enum') or info.get('item_enum')}

        if dry_run:
            print(f"  [DRY_RUN] Would add {len(enum_fields)} enumeration columns to dataset")
            return True

        dataset = Dataset(dataset_id).get()

        for attr_name, info in enum_fields.items():
            # Get enum values (handle both direct enum and item_enum for arrays)
            enum_values = info.get('enum') or info.get('item_enum')
            if enum_values:
                try:
                    # Filter out empty values
                    enum_values = [str(v) for v in enum_values if v and str(v).strip()]
                    if enum_values:
                        column = Column(
                            name=attr_name,
                            column_type=ColumnType.STRING,
                            facet_type=FacetType.enumeration,
                            enum_values=enum_values
                        )
                        dataset.add_column(column)
                except Exception as e:
                    print(f"    ⚠️  Could not add column {attr_name}: {e}")

        dataset.store()
        print(f"  ✓ Added {len(enum_fields)} enumeration columns to dataset")
        return True

    except Exception as e:
        print(f"  ✗ Error adding columns: {e}")
        return False


# ==================== ADVANCED FEATURES ====================

def move_files_to_release(syn, staging_folder_id, file_ids, release_folder_id,
                         move_mode='folder', dry_run=True, verbose=False):
    """
    Move files from staging to release folder.

    Args:
        syn: Synapse client
        staging_folder_id: Staging folder Synapse ID (for folder mode)
        file_ids: List of file Synapse IDs (for individual mode)
        release_folder_id: Target release folder Synapse ID
        move_mode: 'folder' to move entire folder, 'individual' to move files one by one
        dry_run: If True, only show what would be done
        verbose: Show detailed output

    Returns:
        Tuple of (success_count, error_count)
    """
    success_count = 0
    error_count = 0

    if move_mode == 'folder' and staging_folder_id:
        # Move all files within staging folder to release folder (not the folder itself)
        print(f"Moving files from staging folder {staging_folder_id} to release folder {release_folder_id}")

        if dry_run:
            print(f"  [DRY_RUN] Would move {len(file_ids)} files from {staging_folder_id} to {release_folder_id}")
            return len(file_ids), 0
        else:
            try:
                # Use Folder.sync_from_synapse to get all files recursively
                folder = Folder(id=staging_folder_id)
                folder = folder.sync_from_synapse(download_file=False, recursive=True)
                results = folder.files

                print(f"  Found {len(results)} files to move")

                for item in results:
                    try:
                        file = File(id=item.id, download_file=False).get()
                        file.parent_id = release_folder_id
                        file = file.store()
                        if verbose:
                            print(f"  ✓ Moved {file.name} to {release_folder_id}")
                        success_count += 1
                    except Exception as e:
                        print(f"  ✗ Error moving {item.id}: {e}")
                        error_count += 1

                print(f"  ✓ Moved {success_count} files to release folder")
                return success_count, error_count
            except Exception as e:
                print(f"  ✗ Error accessing staging folder: {e}")
                return 0, len(file_ids)

    else:
        # Move individual files
        print(f"Moving {len(file_ids)} files to release folder {release_folder_id}")

        for file_id in file_ids:
            try:
                file_entity = File(id=file_id, download_file=False).get()
                filename = file_entity.name

                if dry_run:
                    print(f"  [DRY_RUN] Would move {filename} ({file_id}) to {release_folder_id}")
                    success_count += 1
                else:
                    file_entity.parent_id = release_folder_id
                    file_entity = file_entity.store()
                    if verbose:
                        print(f"  ✓ Moved {filename} ({file_id})")
                    success_count += 1

            except Exception as e:
                print(f"  ✗ Error moving {file_id}: {e}")
                error_count += 1

        return success_count, error_count


def set_file_versions(syn, file_ids, version_label, version_comment=None, dry_run=True, verbose=False):
    """
    Set version labels on files.

    Args:
        syn: Synapse client
        file_ids: List of file Synapse IDs
        version_label: Version label to apply (e.g., "v1.0")
        version_comment: Optional version comment
        dry_run: If True, only show what would be done
        verbose: Show detailed output

    Returns:
        Tuple of (success_count, error_count)
    """
    if not version_label:
        return 0, 0

    print(f"Setting version label '{version_label}' on {len(file_ids)} files")

    success_count = 0
    error_count = 0

    for file_id in file_ids:
        try:
            if dry_run:
                file_entity = syn.get(file_id, downloadFile=False)
                print(f"  [DRY_RUN] Would set version '{version_label}' on {file_entity.name}")
                success_count += 1
            else:
                file_entity = syn.get(file_id, downloadFile=False)
                file_entity.versionLabel = version_label
                if version_comment:
                    file_entity.versionComment = version_comment
                syn.store(file_entity, forceVersion=True)

                if verbose:
                    print(f"  ✓ Set version '{version_label}' on {file_entity.name}")
                success_count += 1

        except Exception as e:
            print(f"  ✗ Error setting version on {file_id}: {e}")
            error_count += 1

    return success_count, error_count


def generate_wiki_with_ai(dataset_name, dataset_annotations, file_list, dataset_config, timeout=60):
    """
    Use Gemini AI to generate wiki content based on dataset information.

    Args:
        dataset_name: Dataset name
        dataset_annotations: Dataset annotation dict
        file_list: List of file names in dataset
        dataset_config: Dataset config dict (may contain contact, contributors, etc.)
        timeout: Timeout in seconds

    Returns:
        Wiki markdown content, or None if AI fails
    """
    # Create prompt for Gemini
    prompt = f"""Generate a dataset documentation wiki in markdown format for a research dataset.

Dataset Name: {dataset_name}

Dataset Metadata:
{json.dumps(dataset_annotations, indent=2)}

Files in Dataset ({len(file_list)} files):
{', '.join(file_list[:10])}{'...' if len(file_list) > 10 else ''}

Additional Information from Config:
{json.dumps(dataset_config, indent=2)}

Please generate documentation using this EXACT template structure:

**Summary:** [Write a comprehensive 2-3 sentence summary describing the study, its purpose, key findings, and data availability]

**Overall Design:**
- [Study design point 1]
- [Study design point 2]
- [Study design point 3]
- [Additional design details as bullet points]

<details>

<summary>Show More</summary>

<b>Contact:</b>

- [Principal Investigator name, credentials, email]
- [Institution/Department]

<b>Contributors:</b> [List all contributors as comma-separated names]

<b>Publication:</b>

- [Citation with authors, title, journal, year, DOI]
- [**DOI:** DOI_NUMBER](DOI_URL)

</details>

IMPORTANT INSTRUCTIONS:
1. Return ONLY the markdown content, no additional text
2. Use the EXACT template structure above
3. Fill in details based on the dataset metadata provided
4. If information is missing, use placeholder text like "[To be added]"
5. For Contact section, extract from dataset annotations if available
6. For Contributors, use dataset metadata if available
7. For Publication, check for DOI or publication info in metadata
8. Keep the <details> section exactly as shown
9. Make the Summary concise but informative (2-3 sentences)
10. Overall Design should have 4-6 bullet points describing methodology

Generate the wiki content now:"""

    # Check if gemini is available
    if not check_gemini_available():
        print("  ⚠️  Gemini CLI not found - skipping AI wiki generation")
        return None

    try:
        # Run gemini with the prompt
        result = subprocess.run(
            ['gemini', '--yolo'],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        if result.returncode == 0 and result.stdout.strip():
            wiki_content = result.stdout.strip()
            # Remove any markdown code blocks if present
            if wiki_content.startswith('```'):
                lines = wiki_content.split('\n')
                wiki_content = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])
            return wiki_content
        else:
            print(f"  ⚠️  Gemini returned no content or error")
            return None

    except subprocess.TimeoutExpired:
        print(f"  ⚠️  Gemini timed out after {timeout} seconds")
        return None
    except Exception as e:
        print(f"  ⚠️  Error running Gemini: {e}")
        return None


def create_basic_wiki_template(dataset_name, dataset_annotations, file_count, dataset_config):
    """
    Create basic wiki content using the template structure.

    Args:
        dataset_name: Dataset name
        dataset_annotations: Dataset annotation dict
        file_count: Number of files in dataset
        dataset_config: Dataset config dict

    Returns:
        Wiki markdown content
    """
    # Extract information
    summary = dataset_annotations.get('description', '[Dataset description to be added]')
    study_type = dataset_annotations.get('studyType', ['[Study type]'])
    study_design = dataset_annotations.get('studyDesign', '[Study design]')
    data_types = dataset_annotations.get('dataType', ['[Data type]'])

    # Format as list if needed
    if isinstance(study_type, list):
        study_type = ', '.join(study_type)
    if isinstance(data_types, list):
        data_types = ', '.join(data_types)

    # Get contact, contributors, publications from config
    contact = dataset_config.get('contact', '[Principal Investigator, email@institution.edu]')
    institution = dataset_config.get('institution', '[Institution/Department]')
    contributors = dataset_config.get('contributors', '[List of contributors]')
    publication = dataset_config.get('publication', '[Citation information]')
    doi = dataset_config.get('doi', '')
    doi_url = f"https://doi.org/{doi}" if doi else "#"

    # Build wiki content using template
    wiki_content = f"""**Summary:** {summary}

**Overall Design:**
- Study Type: {study_type}
- Study Design: {study_design}
- Data Types: {data_types}
- Total Files: {file_count}

<details>

<summary>Show More</summary>

<b>Contact:</b>

- {contact}
- {institution}

<b>Contributors:</b> {contributors}

<b>Publication:</b>

- {publication}
{f'- [**DOI:** {doi}]({doi_url})' if doi else ''}

</details>
"""

    return wiki_content


def generate_dataset_wiki(syn, dataset_id, dataset_name, dataset_annotations, file_count,
                          file_list=None, dataset_config=None, custom_content=None,
                          use_ai=True, ai_timeout=60, dry_run=True):
    """
    Generate and attach a wiki to the dataset.

    Args:
        syn: Synapse client
        dataset_id: Dataset Synapse ID
        dataset_name: Dataset name
        dataset_annotations: Dataset annotation dict
        file_count: Number of files in dataset
        file_list: List of file names (optional, for AI context)
        dataset_config: Dataset config dict (optional, for contact info, etc.)
        custom_content: Optional custom markdown content (overrides everything)
        use_ai: Use AI to generate wiki content
        ai_timeout: Timeout for AI generation
        dry_run: If True, only show what would be created

    Returns:
        Wiki ID if created, None otherwise
    """
    dataset_config = dataset_config or {}

    # Priority: custom_content > AI-generated > basic template
    if custom_content:
        wiki_content = custom_content
    elif use_ai:
        print("  🤖 Generating wiki content with AI...")
        wiki_content = generate_wiki_with_ai(
            dataset_name, dataset_annotations, file_list or [],
            dataset_config, ai_timeout
        )
        if not wiki_content:
            print("  ⚠️  AI generation failed, using basic template")
            wiki_content = create_basic_wiki_template(
                dataset_name, dataset_annotations, file_count, dataset_config
            )
    else:
        wiki_content = create_basic_wiki_template(
            dataset_name, dataset_annotations, file_count, dataset_config
        )

    if dry_run:
        print(f"  [DRY_RUN] Would create wiki for dataset {dataset_id}")
        print(f"  Wiki content preview (first 300 chars):")
        print(f"  {wiki_content[:300]}...")
        return None
    else:
        try:
            wiki = syn.store(Wiki(
                title="Dataset Documentation",
                markdown=wiki_content,
                owner=dataset_id
            ))
            print(f"  ✓ Wiki created successfully with ID: {wiki.id}")
            return wiki.id
        except Exception as e:
            print(f"  ✗ Error creating wiki: {e}")
            return None


def create_dataset_snapshot(syn, dataset_id, version_label, version_comment=None, dry_run=True):
    """
    Create a snapshot/version of the dataset.

    Args:
        syn: Synapse client
        dataset_id: Dataset Synapse ID
        version_label: Version label (e.g., "v1.0", "2026.1")
        version_comment: Optional comment describing the version
        dry_run: If True, only show what would be created

    Returns:
        Snapshot ID if created, None otherwise
    """
    if not version_label:
        return None

    if dry_run:
        print(f"  [DRY_RUN] Would create snapshot '{version_label}' for dataset {dataset_id}")
        if version_comment:
            print(f"    Comment: {version_comment}")
        return None
    else:
        try:
            # Use Dataset.snapshot() API
            dataset = Dataset(id=dataset_id).get(include_columns=True)
            snapshot = dataset.snapshot(
                comment=version_comment or f"Dataset snapshot {version_label}",
                label=version_label
            )
            print(f"  ✅ Created snapshot successfully!")
            print(f"     🏷️  Label: {version_label}")
            print(f"     💬 Comment: {version_comment or f'Dataset snapshot {version_label}'}")
            print(f"     🔗 URL: https://www.synapse.org/#!Synapse:{dataset_id}")
            return dataset_id
        except Exception as e:
            print(f"  ✗ Error creating snapshot: {e}")
            return None


def add_dataset_to_collection(syn, dataset_id, collection_id, dry_run=True):
    """
    Add a dataset to a dataset collection.

    Args:
        syn: Synapse client
        dataset_id: Dataset Synapse ID
        collection_id: DatasetCollection Synapse ID
        dry_run: If True, only show what would be done

    Returns:
        True if successful, False otherwise
    """
    if not collection_id:
        return False

    if dry_run:
        print(f"  [DRY_RUN] Would add dataset {dataset_id} to collection {collection_id}")
        return True
    else:
        try:
            dataset_collection = DatasetCollection(id=collection_id).get()
            dataset = Dataset(id=dataset_id).get(include_columns=True)
            dataset_collection.add_item(dataset)
            dataset_collection.store()
            print(f"  ✅ Added dataset {dataset_id} to collection {collection_id}")
            return True
        except Exception as e:
            print(f"  ✗ Error adding dataset to collection: {e}")
            import traceback
            traceback.print_exc()
            return False


def create_dataset_entity_view(syn, dataset_id, dataset_name, project_id,
                               file_type='ClinicalFile', all_schemas=None, dry_run=True):
    """
    Create an entity view for the dataset files.

    Args:
        syn: Synapse client
        dataset_id: Dataset Synapse ID
        dataset_name: Dataset name
        project_id: Project ID to create view in
        file_type: Type of files (for schema-based columns)
        all_schemas: Schema dictionary
        dry_run: If True, only show what would be created

    Returns:
        Entity view ID if created, None otherwise
    """
    view_name = f"{dataset_name}_EntityView"

    # Get column definitions from schema
    annotation_columns = []
    if all_schemas and file_type in all_schemas:
        schema = all_schemas[file_type]
        field_info = get_field_info(schema)

        # Add key columns (limit to most important ones)
        important_fields = ['dataType', 'fileFormat', 'assay', 'platform',
                           'specimenType', 'sex', 'diagnosis']

        for field_name in important_fields:
            if field_name in field_info:
                info = field_info[field_name]
                # Map JSON types to Synapse column types
                if info['type'] == 'array':
                    col_type = ColumnType.STRING_LIST
                elif info['type'] == 'integer':
                    col_type = ColumnType.INTEGER
                elif info['type'] == 'boolean':
                    col_type = ColumnType.BOOLEAN
                else:
                    col_type = ColumnType.STRING

                annotation_columns.append(Column(
                    name=field_name,
                    column_type=col_type
                ))

    # Build final column list: name column first, then annotation columns
    all_columns = []
    all_columns.append(Column(name="name", column_type=ColumnType.STRING))
    all_columns.extend(annotation_columns)

    if dry_run:
        print(f"  [DRY_RUN] Would create entity view '{view_name}'")
        print(f"    Scope: {dataset_id}")
        print(f"    Columns: {len(all_columns)} columns (name + {len(annotation_columns)} annotations)")
        return None
    else:
        try:
            # Create entity view
            entity_view = EntityView(
                name=view_name,
                parent_id=project_id,
                scope_ids=[dataset_id],
                view_type_mask=ViewTypeMask.FILE | ViewTypeMask.FOLDER,
                columns=all_columns
            )
            # Use entity_view.store() instead of syn.store(view)
            created_view = entity_view.store()
            print(f"  ✓ Entity view created: {created_view.id}")
            print(f"  ✓ Total columns: {len(all_columns)} (name + {len(annotation_columns)} annotations)")
            print(f"  🔗 URL: https://www.synapse.org/#!Synapse:{created_view.id}")
            return created_view.id
        except Exception as e:
            print(f"  ✗ Error creating entity view: {e}")
            import traceback
            traceback.print_exc()
            return None


# ==================== UPDATE WORKFLOW FUNCTIONS ====================

def enumerate_dataset_files(syn, dataset_syn_id, verbose=False):
    """Query all files in a dataset and extract their annotations"""
    print(f"Retrieving files from dataset {dataset_syn_id}...")

    try:
        dataset = Dataset(dataset_syn_id).get()
        results = dataset.items
        annotations_dict = {}
        file_count = 0

        for row in results:
            syn_id = row.id
            try:
                entity = syn.get(syn_id, downloadFile=False)
                filename = entity.name
                annotations = dict(entity.annotations) if hasattr(entity, 'annotations') else {}
                if annotations:
                    annotations_dict[syn_id] = {filename: annotations}
                    file_count += 1
            except Exception as e:
                if verbose:
                    print(f"  ⚠️  Could not get annotations for {syn_id}: {e}")

        print(f"✓ Retrieved annotations for {file_count} files")
        return annotations_dict
    except Exception as e:
        print(f"✗ Error retrieving dataset files: {e}")
        return {}


def enumerate_folder_files(syn, folder_syn_id, verbose=False):
    """Query all files in a Synapse folder and extract their annotations"""
    print(f"Retrieving files from folder {folder_syn_id}...")

    try:
        query_results = list(syn.getChildren(folder_syn_id, includeTypes=["file"]))
        annotations_dict = {}
        file_count = 0

        for item in query_results:
            syn_id = item['id']
            filename = item['name']

            try:
                entity = syn.get(syn_id, downloadFile=False)
                annotations = dict(entity.annotations) if hasattr(entity, 'annotations') else {}
                annotations_dict[syn_id] = {filename: annotations}
                file_count += 1
            except Exception as e:
                if verbose:
                    print(f"  ⚠️  Could not get annotations for {filename}: {e}")

        print(f"✓ Retrieved {file_count} files from folder")
        return annotations_dict
    except Exception as e:
        print(f"✗ Error retrieving folder files: {e}")
        return {}


# ==================== FILE I/O ====================

def load_annotation_file(file_path):
    """Load annotation JSON file"""
    if not os.path.exists(file_path):
        return {}

    with open(file_path, 'r') as f:
        return json.load(f)


def save_annotation_file(annotations_dict, file_path):
    """Save annotations to JSON file"""
    with open(file_path, 'w') as f:
        json.dump(annotations_dict, f, indent=2)
    print(f"✓ Saved annotations to {file_path}")


# ==================== AI-ASSISTED ANNOTATION ====================

def check_gemini_available():
    """Check if gemini CLI is available"""
    try:
        result = subprocess.run(['gemini', '--version'],
                              capture_output=True, text=True, timeout=5)
        return result.returncode == 0 or 'gemini' in result.stderr.lower()
    except:
        return False


def download_file_for_analysis(syn, syn_id, download_dir):
    """Download a Synapse file for AI analysis"""
    try:
        entity = syn.get(syn_id, downloadLocation=download_dir)
        return entity.path
    except Exception as e:
        print(f"  ⚠️  Could not download {syn_id}: {e}")
        return None


def create_annotation_prompt(filename, file_type, all_schemas):
    """Create a prompt for Gemini to extract file annotations"""

    # Get schema and field info
    schema = get_schema_for_type(file_type, all_schemas)
    if not schema:
        return f"Analyze the file {filename} and extract metadata as JSON."

    field_info_dict = get_field_info(schema)
    required_field_names = get_required_fields(schema)

    # Get list of required and optional fields
    required_fields = []
    optional_fields = []

    for field_name, info in field_info_dict.items():
        field_desc = f"- {field_name}"

        if info.get('description'):
            field_desc += f": {info['description']}"

        # Add enum values if present
        if info.get('enum'):
            enum_values = info['enum'][:5]  # First 5 values
            field_desc += f" (allowed values: {', '.join(str(v) for v in enum_values)})"
        elif info.get('item_enum'):
            enum_values = info['item_enum'][:5]
            field_desc += f" (allowed values: {', '.join(str(v) for v in enum_values)})"

        # Indicate if it's an array
        if info['type'] == 'array':
            field_desc += " [can be multiple values as array]"

        # Categorize as required or optional
        if field_name in required_field_names:
            required_fields.append(field_desc)
        else:
            optional_fields.append(field_desc)

    prompt = f"""You are analyzing a data file to extract metadata annotations based on a schema.

File: {filename}
File Type: {file_type}

Task: Analyze this file and extract as many of the following annotations as possible by examining:
- File content (first few rows, column names, data patterns)
- File name and structure
- Data types and formats

REQUIRED FIELDS (must provide):
{chr(10).join(required_fields[:10])}

OPTIONAL FIELDS (provide if determinable):
{chr(10).join(optional_fields[:15])}

IMPORTANT INSTRUCTIONS:
1. Return ONLY valid JSON (no markdown, no explanations)
2. Use field names exactly as shown above
3. For multivalued fields, return as array: ["value1", "value2"]
4. For enum fields, use ONLY the allowed values listed
5. If you cannot determine a value, use empty string "" or empty array []
6. Be conservative - only provide values you're confident about
7. For clinical/demographic data, look for common patterns (demographics, assessments, visits)
8. For omic data, look for assay types, platforms, measurement types

Example output format:
{{
  "dataType": "clinical",
  "fileFormat": "csv",
  "specimenType": [""],
  "assay": "",
  "description": "Clinical demographic data with patient information"
}}

Now analyze the file and return ONLY the JSON object with extracted annotations:"""

    return prompt


def run_gemini_on_file(file_path, prompt, timeout=60):
    """
    Run gemini CLI on a file with a prompt.
    Returns: parsed JSON dict or None
    """
    try:
        # Build command - pass file content via stdin and prompt as argument
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            # Read first 100 lines to avoid overwhelming the model
            lines = []
            for i, line in enumerate(f):
                if i >= 100:
                    break
                lines.append(line)
            file_content = ''.join(lines)

        # Create full prompt with file content
        full_prompt = f"{prompt}\n\nFILE CONTENT (first 100 lines):\n{file_content}"

        # Run gemini
        result = subprocess.run(
            ['gemini', '--yolo', full_prompt],
            capture_output=True,
            text=True,
            timeout=timeout
        )

        if result.returncode != 0:
            print(f"    ⚠️  Gemini returned non-zero exit code")
            return None

        # Parse output - look for JSON
        output = result.stdout.strip()

        # Try to extract JSON from markdown code blocks if present
        if '```json' in output:
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', output, re.DOTALL)
            if json_match:
                output = json_match.group(1)
        elif '```' in output:
            json_match = re.search(r'```\s*(\{.*?\})\s*```', output, re.DOTALL)
            if json_match:
                output = json_match.group(1)

        # Try to parse JSON
        try:
            annotations = json.loads(output)
            return annotations
        except json.JSONDecodeError:
            # Try to find JSON object in output
            json_match = re.search(r'\{.*\}', output, re.DOTALL)
            if json_match:
                try:
                    annotations = json.loads(json_match.group(0))
                    return annotations
                except:
                    pass

            print(f"    ⚠️  Could not parse Gemini output as JSON")
            return None

    except subprocess.TimeoutExpired:
        print(f"    ⚠️  Gemini timed out after {timeout}s")
        return None
    except Exception as e:
        print(f"    ⚠️  Error running Gemini: {e}")
        return None


def enhance_annotations_with_ai(syn, files_dict, annotations_dict, all_schemas,
                                download_dir, config):
    """
    Download files and use Gemini to enhance annotations.

    Args:
        syn: Synapse client
        files_dict: {syn_id: {'name': filename, 'path': folder_path, 'annotations': {}}}
        annotations_dict: {syn_id: {filename: {annotations}}}
        all_schemas: Schema definitions
        download_dir: Where to download files
        config: Config object with AI settings

    Returns:
        Enhanced annotations_dict
    """
    print("\n" + "=" * 60)
    print("AI-ASSISTED ANNOTATION (Gemini)")
    print("=" * 60)

    # Check if gemini is available
    if not check_gemini_available():
        print("⚠️  Gemini CLI not found - skipping AI enhancement")
        print("   Install from: https://github.com/google-gemini/gemini-cli")
        return annotations_dict

    print(f"✓ Gemini CLI detected (model: {config.AI_MODEL})")

    # Create download directory
    os.makedirs(download_dir, exist_ok=True)

    enhanced_count = 0
    failed_count = 0
    skipped_count = 0

    for syn_id, file_info in files_dict.items():
        filename = file_info['name']

        # Skip non-data files
        if not filename.lower().endswith(('.csv', '.tsv', '.txt', '.json')):
            if config.VERBOSE:
                print(f"  ⊘ Skipping {filename} (not a data file)")
            skipped_count += 1
            continue

        print(f"\n  Analyzing: {filename}")

        # Download file
        print(f"    ↓ Downloading...")
        local_path = download_file_for_analysis(syn, syn_id, download_dir)

        if not local_path:
            failed_count += 1
            continue

        # Get file type and schema
        file_data = annotations_dict.get(syn_id, {})
        current_annotations = file_data.get(filename, {})
        file_type = current_annotations.get('_file_type', 'ClinicalFile')

        # Create prompt (now uses all_schemas directly)
        prompt = create_annotation_prompt(filename, file_type, all_schemas)

        # Run Gemini
        print(f"    🤖 Running Gemini AI...")
        ai_annotations = run_gemini_on_file(local_path, prompt, timeout=config.AI_TIMEOUT)

        if ai_annotations:
            # Merge AI annotations with existing template
            # Priority: existing manual values > AI values > template defaults
            enhanced = current_annotations.copy()

            for key, value in ai_annotations.items():
                # Only add if not already filled and not empty
                if key in enhanced and enhanced[key] in ["", [""], [], None]:
                    if value not in ["", [""], [], None]:
                        enhanced[key] = value
                        if config.VERBOSE:
                            print(f"      + {key}: {value}")

            annotations_dict[syn_id][filename] = enhanced
            enhanced_count += 1
            print(f"    ✓ Enhanced with AI annotations")
        else:
            failed_count += 1
            print(f"    ✗ AI annotation failed")

    print("\n" + "=" * 60)
    print("AI ENHANCEMENT SUMMARY")
    print("=" * 60)
    print(f"  ✓ Enhanced: {enhanced_count} files")
    print(f"  ✗ Failed: {failed_count} files")
    print(f"  ⊘ Skipped: {skipped_count} files")
    print("=" * 60)

    return annotations_dict


def enhance_dataset_annotations_with_ai(dataset_name, file_annotations, all_schemas, dataset_type, config):
    """
    Use Gemini AI to generate dataset-level annotations based on file annotations.

    Args:
        dataset_name: Name of the dataset
        file_annotations: Dict of file annotations {syn_id: {filename: annotations}}
        all_schemas: Dict of schemas
        dataset_type: Dataset type (e.g., 'ClinicalDataset')
        config: Config object

    Returns:
        Enhanced dataset annotation dict
    """
    if not check_gemini_available():
        print("  ⚠️  Gemini CLI not found - using template only")
        return create_annotation_template(all_schemas, dataset_type)

    print("  🤖 Generating dataset annotations with AI...")

    # Collect file summaries
    file_summaries = []
    for syn_id, file_data in list(file_annotations.items())[:10]:  # Sample first 10 files
        filename = list(file_data.keys())[0]
        annotations = file_data[filename]
        file_summaries.append({
            'filename': filename,
            'dataType': annotations.get('dataType', ''),
            'fileFormat': annotations.get('fileFormat', ''),
            'assay': annotations.get('assay', []),
            'platform': annotations.get('platform', '')
        })

    # Get schema info
    schema = get_schema_for_type(dataset_type, all_schemas)
    field_info = get_field_info(schema) if schema else {}
    required_fields = get_required_fields(schema) if schema else []

    # Build field descriptions with enum values - ONLY dataset-level fields
    # Exclude file-level fields that shouldn't be in dataset annotations
    file_level_fields = {
        'assay', 'platform', 'specimenType', 'cellType', 'libraryLayout',
        'FACSPopulation', 'GEOSuperSeries', 'biospecimenType', 'originalSampleName',
        'fileFormat', 'sex', 'age', 'diagnosis', 'tissueType'
    }

    field_descriptions = []
    for field_name, info in list(field_info.items())[:25]:
        # Skip file-level fields
        if field_name in file_level_fields:
            continue

        desc = f"- {field_name} ({info['type']})"
        if info.get('description'):
            desc += f": {info['description']}"
        if info.get('enum'):
            enum_values = [str(v) for v in info['enum'][:15] if v and str(v).strip()]
            if enum_values:
                desc += f" [MUST use one of: {', '.join(enum_values)}]"
        elif info.get('item_enum'):
            enum_values = [str(v) for v in info['item_enum'][:15] if v and str(v).strip()]
            if enum_values:
                desc += f" [array - use values from: {', '.join(enum_values)}]"
        field_descriptions.append(desc)

    # Create prompt
    prompt = f"""Generate DATASET-LEVEL annotations for a research dataset based on the files it contains.

Dataset Name: {dataset_name}
Dataset Type: {dataset_type}
Total Files: {len(file_annotations)}

Sample Files and Their Annotations:
{json.dumps(file_summaries, indent=2)}

Dataset Schema Fields (DATASET-LEVEL ONLY - with allowed values):
{chr(10).join(field_descriptions)}

Required Fields: {', '.join([f for f in required_fields[:10] if f not in file_level_fields])}

CRITICAL INSTRUCTIONS:
1. Generate ONLY dataset-level metadata (NOT file-level fields like assay, platform, etc.)
2. studyType: MUST be a STRING, not an array. Pick ONE value from the enum list.
3. dataType: MUST be an ARRAY of values from the enum list (e.g., ["clinical_assessment", "treatment"])
4. clinicalDomain: MUST be an ARRAY of values from the enum list
5. collection: MUST be an ARRAY of values from the enum list
6. creator: MUST be an ARRAY of strings (e.g., ["Sage Bionetworks", "Author Name"])
7. species: MUST be an ARRAY of values from the enum list
8. For enum fields, use ONLY the exact values from the allowed list
9. Do NOT include file-level fields (assay, platform, cellType, specimenType, etc.)
10. Return ONLY valid JSON with no markdown
11. Use empty arrays [] for unknown multi-value fields, not [""]
12. Use null or empty string "" for unknown single-value fields
13. datePublished should be an integer year (e.g., 2026) or null

IMPORTANT:
- studyType is a STRING (e.g., "Clinical Trial")
- Do NOT include file-level fields
- Use exact enum values only
- Empty arrays should be [], not [""]

Generate the dataset annotations JSON now:"""

    try:
        result = subprocess.run(
            ['gemini', '--yolo'],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=config.AI_TIMEOUT
        )

        if result.returncode == 0 and result.stdout.strip():
            ai_output = result.stdout.strip()

            # Remove markdown code blocks if present
            if '```json' in ai_output:
                ai_output = ai_output.split('```json')[1].split('```')[0].strip()
            elif '```' in ai_output:
                lines = ai_output.split('\n')
                ai_output = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])

            # Parse JSON
            try:
                ai_annotations = json.loads(ai_output)

                # Merge with template
                template = create_annotation_template(all_schemas, dataset_type)
                for key, value in ai_annotations.items():
                    if key in template and value not in ["", [""], [], None]:
                        template[key] = value

                print(f"  ✓ Dataset annotations enhanced with AI")
                return template

            except json.JSONDecodeError as e:
                print(f"  ⚠️  Could not parse AI output as JSON: {e}")
                return create_annotation_template(all_schemas, dataset_type)
        else:
            print(f"  ⚠️  Gemini returned no content")
            return create_annotation_template(all_schemas, dataset_type)

    except subprocess.TimeoutExpired:
        print(f"  ⚠️  Gemini timed out")
        return create_annotation_template(all_schemas, dataset_type)
    except Exception as e:
        print(f"  ⚠️  Error running Gemini: {e}")
        return create_annotation_template(all_schemas, dataset_type)


# ==================== COMMAND HANDLERS ====================

def handle_create_workflow(args, config):
    """Handle CREATE workflow - create new dataset from scratch"""
    print("\n" + "=" * 60)
    print("WORKFLOW: CREATE NEW DATASET")
    print("=" * 60)

    if not args.staging_folder:
        print("❌ Error: --staging-folder required for CREATE workflow")
        sys.exit(1)

    if not args.dataset_name:
        print("❌ Error: --dataset-name required for CREATE workflow")
        sys.exit(1)

    # Load schemas
    print("\nLoading schemas...")
    all_schemas = get_all_schemas(config.SCHEMA_BASE_PATH, config.VERBOSE)

    # Get dataset-specific configuration (for type detection)
    dataset_config = config.get_dataset_config(args.dataset_name)
    if dataset_config.get('dataset_type'):
        print(f"Using configured dataset type: {dataset_config['dataset_type']}")

    # Connect to Synapse
    print("\nConnecting to Synapse...")
    syn = connect_to_synapse(config)

    # Step 1: Enumerate files
    print("\n" + "=" * 60)
    print("STEP 1: ENUMERATING FILES")
    print("=" * 60)
    files_dict = enumerate_files_with_folders(
        syn, args.staging_folder, recursive=True, verbose=config.VERBOSE
    )

    if not files_dict:
        print("❌ No files found in staging folder")
        sys.exit(1)

    # Step 2: Generate annotation templates
    print("\n" + "=" * 60)
    print("STEP 2: GENERATING ANNOTATION TEMPLATES")
    print("=" * 60)

    annotations_output = {}
    for syn_id, file_info in files_dict.items():
        filename = file_info['name']
        existing_annotations = file_info['annotations']

        # Detect file type (checks config first, then pattern matching, then defaults to File)
        file_type = detect_file_type(filename, all_schemas=all_schemas, dataset_config=dataset_config)

        # Create template
        template = create_annotation_template(all_schemas, file_type)

        # Smart merge with existing
        merged = merge_annotations_smartly(existing_annotations, template)

        annotations_output[syn_id] = {filename: merged}

    # Step 3: AI-Assisted Annotation Enhancement
    if config.AI_ENABLED:
        download_dir = os.path.join(config.BASE_DIR, "downloads", args.dataset_name.replace(" ", "_"))
        annotations_output = enhance_annotations_with_ai(
            syn, files_dict, annotations_output, all_schemas,
            download_dir, config
        )

    # Save annotations
    output_file = os.path.join(config.ANNOTATIONS_DIR, f"{args.dataset_name}_annotations.json")
    save_annotation_file(annotations_output, output_file)

    # Generate dataset annotation template (checks config first, then pattern matching, then defaults to Dataset)
    print("\n" + "=" * 60)
    print("GENERATING DATASET ANNOTATIONS")
    print("=" * 60)
    dataset_type = detect_dataset_type(args.dataset_name, args.staging_folder, dataset_config=dataset_config)

    # Use AI to generate dataset annotations if enabled
    if config.AI_ENABLED:
        dataset_template = enhance_dataset_annotations_with_ai(
            args.dataset_name, annotations_output, all_schemas, dataset_type, config
        )
    else:
        dataset_template = create_annotation_template(all_schemas, dataset_type)

    dataset_output_file = os.path.join(config.ANNOTATIONS_DIR, f"{args.dataset_name}_dataset_annotations.json")
    save_annotation_file(dataset_template, dataset_output_file)

    print("\n" + "=" * 60)
    print("✅ TEMPLATE GENERATION COMPLETE")
    print("=" * 60)
    print(f"File annotations: {output_file}")
    print(f"Dataset annotations: {dataset_output_file}")
    print(f"Total files: {len(annotations_output)}")
    print("\n⚠️  MANUAL STEP: Edit the annotation files")
    print(f"\nAfter editing, continue with:")
    print(f"  python {sys.argv[0]} create --from-annotations \\" )
    print(f"    --staging-folder {args.staging_folder} \\")
    print(f"    --dataset-name {args.dataset_name}")


def handle_create_from_annotations(args, config):
    """Handle CREATE workflow from pre-edited annotations"""
    print("\n" + "=" * 60)
    print("WORKFLOW: CREATE DATASET FROM ANNOTATIONS")
    print("=" * 60)

    # Load annotations
    file_annotations_file = os.path.join(config.ANNOTATIONS_DIR, f"{args.dataset_name}_annotations.json")
    dataset_annotations_file = os.path.join(config.ANNOTATIONS_DIR, f"{args.dataset_name}_dataset_annotations.json")

    file_annotations = load_annotation_file(file_annotations_file)
    dataset_annotations = load_annotation_file(dataset_annotations_file)

    if not file_annotations:
        print(f"❌ No file annotations found at {file_annotations_file}")
        sys.exit(1)

    # Load schemas
    all_schemas = get_all_schemas(config.SCHEMA_BASE_PATH, config.VERBOSE)

    # Connect to Synapse
    syn = connect_to_synapse(config)

    # Validate annotations
    print("\n" + "=" * 60)
    print("STEP 1: VALIDATING ANNOTATIONS")
    print("=" * 60)

    # Validate file annotations
    print("\nValidating file annotations...")
    file_annotations_valid = True
    for syn_id, file_data in file_annotations.items():
        filename = list(file_data.keys())[0]
        annotations = file_data[filename]
        file_type = annotations.get('_file_type', 'ClinicalFile')

        is_valid, errors, warnings = validate_annotation_against_schema(
            annotations, file_type, all_schemas
        )

        if not is_valid:
            print(f"  ✗ {filename}: {len(errors)} errors")
            for error in errors:
                print(f"      - {error}")
            file_annotations_valid = False

    if file_annotations_valid:
        print("  ✓ All file annotations valid")

    # Validate dataset annotations
    print("\nValidating dataset annotations...")
    dataset_annotations_valid = True
    if dataset_annotations:
        # Get dataset config to determine correct type
        dataset_config = config.get_dataset_config(args.use_config) if hasattr(args, 'use_config') and args.use_config else {}

        # Detect dataset type (checks config first, then pattern matching, then defaults to Dataset)
        dataset_type = dataset_annotations.get('_dataset_type')
        if not dataset_type:
            dataset_type = detect_dataset_type(
                args.dataset_name,
                args.staging_folder if hasattr(args, 'staging_folder') else None,
                dataset_config=dataset_config
            )
            # Add the detected type to annotations
            dataset_annotations['_dataset_type'] = dataset_type

        print(f"  Using schema: {dataset_type}")
        is_valid, errors, warnings = validate_annotation_against_schema(
            dataset_annotations, dataset_type, all_schemas
        )

        if not is_valid:
            print(f"  ✗ Dataset annotations: {len(errors)} errors")
            for error in errors:
                print(f"      - {error}")
            dataset_annotations_valid = False
        else:
            print("  ✓ Dataset annotations valid")

    # Check overall validity
    all_valid = file_annotations_valid and dataset_annotations_valid

    if not all_valid:
        print("\n" + "=" * 60)
        print("❌ VALIDATION FAILED")
        print("=" * 60)
        if not file_annotations_valid:
            print("  ✗ File annotations have errors")
        if not dataset_annotations_valid:
            print("  ✗ Dataset annotations have errors")

        print("\nYou have the following options:")
        print("  1. Fix the errors and run again")
        print("  2. Proceed anyway (not recommended - may cause issues)")
        print("  3. Exit and fix manually")

        # Prompt user
        while True:
            try:
                response = input("\nProceed with invalid annotations? (yes/no): ").strip().lower()
                if response in ['yes', 'y']:
                    print("\n⚠️  WARNING: Proceeding with invalid annotations!")
                    print("   This may cause issues with dataset creation.")
                    break
                elif response in ['no', 'n']:
                    print("\n✓ Exiting. Please fix validation errors and try again.")
                    sys.exit(1)
                else:
                    print("Please answer 'yes' or 'no'")
            except (EOFError, KeyboardInterrupt):
                print("\n\n✓ Exiting.")
                sys.exit(1)
    else:
        print("\n✓ All annotations valid (files and dataset)")

    # Get dataset config for advanced features
    dataset_config = config.get_dataset_config(args.use_config) if hasattr(args, 'use_config') and args.use_config else {}

    # Debug: Show what config was retrieved
    if config.VERBOSE:
        print(f"\n[DEBUG] Retrieved dataset_config keys: {list(dataset_config.keys())}")
        print(f"[DEBUG] generate_wiki: {dataset_config.get('generate_wiki', False)}")
        print(f"[DEBUG] create_snapshot: {dataset_config.get('create_snapshot', False)}")
        print(f"[DEBUG] create_entity_view: {dataset_config.get('create_entity_view', False)}")

    # ========== PHASE 2: FILE ANNOTATION & VALIDATION ==========

    # STEP 2: Apply annotations to files in staging folder
    print("\n" + "=" * 60)
    print("PHASE 2: FILE ANNOTATION & VALIDATION")
    print("=" * 60)
    print("\n" + "=" * 60)
    print("STEP 2: APPLYING ANNOTATIONS TO FILES")
    print("=" * 60)

    file_ids = list(file_annotations.keys())
    success, errors = apply_annotations_to_files(
        syn, file_annotations, config.DRY_RUN, config.VERBOSE
    )
    print(f"✓ Applied: {success}, Errors: {errors}")

    # STEP 3: Create entity view (SCOPED TO STAGING FOLDER, NOT DATASET)
    print("\n" + "=" * 60)
    print("STEP 3: CREATING ENTITY VIEW FOR STAGING FOLDER")
    print("=" * 60)
    print("⚠️  Entity view is scoped to STAGING FOLDER for validation")

    # Detect predominant file type
    file_type = dataset_annotations.get('_dataset_type', 'ClinicalDataset').replace('Dataset', 'File')

    view_id = create_dataset_entity_view(
        syn, args.staging_folder, args.dataset_name, config.SYNAPSE_PROJECT_ID,
        file_type, all_schemas, config.DRY_RUN
    )

    if view_id:
        print(f"\n✅ Entity view created for validation!")
        print(f"   🔗 View in Synapse: https://www.synapse.org/#!Synapse:{view_id}")
        print(f"   📊 Review all file annotations in the entity view")

    # PAUSE: Prompt user to verify annotations in entity view
    print("\n" + "=" * 60)
    print("⏸️  VERIFICATION CHECKPOINT")
    print("=" * 60)
    print("\n⚠️  IMPORTANT: Please verify your file annotations!")
    print(f"\n1. Open the entity view in Synapse:")
    print(f"   🔗 https://www.synapse.org/#!Synapse:{view_id}")
    print(f"\n2. Review all file annotations to ensure they are correct")
    print(f"\n3. Once verified, return here to continue")

    # Prompt user to continue
    while True:
        try:
            response = input("\nHave you verified the annotations? Ready to continue? (yes/no): ").strip().lower()
            if response in ['yes', 'y']:
                print("\n✓ Continuing with workflow...")
                break
            elif response in ['no', 'n']:
                print("\n✓ Exiting. Please verify annotations and run again.")
                print(f"\nTo resume, run:")
                print(f"  python {sys.argv[0]} create --use-config {args.use_config if hasattr(args, 'use_config') else args.dataset_name} --from-annotations --execute")
                sys.exit(0)
            else:
                print("Please answer 'yes' or 'no'")
        except (EOFError, KeyboardInterrupt):
            print("\n\n✓ Exiting.")
            sys.exit(0)

    # STEP 4: Set version labels on files (BEFORE dataset creation)
    version_label = dataset_config.get('version_label') if dataset_config else (args.version_label if hasattr(args, 'version_label') and args.version_label else None)
    version_comment = dataset_config.get('version_comment') if dataset_config else (args.version_comment if hasattr(args, 'version_comment') and args.version_comment else None)
    if config.VERBOSE:
        print(f"[DEBUG] version_label: {version_label}, version_comment: {version_comment}")
    if version_label:
        print("\n" + "=" * 60)
        print("STEP 4: SETTING FILE VERSION LABELS")
        print("=" * 60)
        success, errors = set_file_versions(syn, file_ids, version_label, version_comment, config.DRY_RUN, config.VERBOSE)
        print(f"✓ Versioned: {success}, Errors: {errors}")

    # ========== PHASE 3: DATASET CREATION & FINALIZATION ==========

    print("\n" + "=" * 60)
    print("PHASE 3: DATASET CREATION & FINALIZATION")
    print("=" * 60)

    # STEP 5: Create dataset entity
    print("\n" + "=" * 60)
    print("STEP 5: CREATING DATASET ENTITY")
    print("=" * 60)

    dataset_id = create_dataset_entity(
        syn, args.dataset_name, dataset_annotations,
        config.SYNAPSE_PROJECT_ID, all_schemas, config.DRY_RUN
    )

    if not dataset_id:
        print("❌ Failed to create dataset")
        sys.exit(1)

    # STEP 6: Add files to dataset
    print("\n" + "=" * 60)
    print("STEP 6: ADDING FILES TO DATASET")
    print("=" * 60)

    add_files_to_dataset(syn, dataset_id, file_ids, config.DRY_RUN)

    # STEP 7: Add columns for faceted search
    print("\n" + "=" * 60)
    print("STEP 7: ADDING DATASET COLUMNS")
    print("=" * 60)

    add_dataset_columns(syn, dataset_id, all_schemas, file_type, config.DRY_RUN)

    # STEP 8: Generate wiki (if requested)
    generate_wiki = dataset_config.get('generate_wiki', False) if dataset_config else (args.generate_wiki if hasattr(args, 'generate_wiki') else False)
    if config.VERBOSE:
        print(f"[DEBUG] generate_wiki condition: {generate_wiki} (from config: {dataset_config.get('generate_wiki', 'N/A') if dataset_config else 'N/A'})")
    if generate_wiki:
        print("\n" + "=" * 60)
        print("STEP 8: GENERATING DATASET WIKI")
        print("=" * 60)

        # Load custom wiki content if provided
        custom_content = None
        if hasattr(args, 'wiki_content') and args.wiki_content:
            try:
                with open(args.wiki_content, 'r') as f:
                    custom_content = f.read()
            except Exception as e:
                print(f"  ⚠️  Warning: Could not load wiki content from {args.wiki_content}: {e}")

        # Check for wiki_content in dataset config
        if not custom_content and 'wiki_content' in dataset_config:
            custom_content = dataset_config['wiki_content']

        # Get file list for AI context
        file_list = [list(file_data.keys())[0] for file_data in file_annotations.values()]

        wiki_id = generate_dataset_wiki(
            syn, dataset_id, args.dataset_name, dataset_annotations,
            len(file_ids),
            file_list=file_list,
            dataset_config=dataset_config,
            custom_content=custom_content,
            use_ai=config.AI_ENABLED,
            ai_timeout=config.AI_TIMEOUT,
            dry_run=config.DRY_RUN
        )
        if wiki_id:
            print(f"✓ Wiki ID: {wiki_id}")

    # STEP 9: Set acknowledgement statement (if provided)
    acknowledgement_statement = dataset_config.get('acknowledgementStatement')
    if acknowledgement_statement:
        print("\n" + "=" * 60)
        print("STEP 9: SETTING ACKNOWLEDGEMENT STATEMENT")
        print("=" * 60)
        if config.DRY_RUN:
            print(f"  [DRY_RUN] Would set acknowledgementStatement: {acknowledgement_statement}")
        else:
            try:
                dataset = syn.get(dataset_id, downloadFile=False)
                dataset.annotations['acknowledgementStatement'] = acknowledgement_statement
                syn.store(dataset, forceVersion=False)
                print(f"  ✓ Acknowledgement statement set")
            except Exception as e:
                print(f"  ✗ Error setting acknowledgement statement: {e}")

    # STEP 10: Create dataset snapshot (if requested)
    create_snapshot = dataset_config.get('create_snapshot', False) if dataset_config else (args.create_snapshot if hasattr(args, 'create_snapshot') else False)
    if config.VERBOSE:
        print(f"[DEBUG] create_snapshot condition: {create_snapshot}, version_label: {version_label}")
    if create_snapshot and version_label:
        print("\n" + "=" * 60)
        print("STEP 10: CREATING DATASET SNAPSHOT")
        print("=" * 60)
        snapshot_version = create_dataset_snapshot(syn, dataset_id, version_label, version_comment, config.DRY_RUN)
        if snapshot_version:
            print(f"✓ Snapshot version: {snapshot_version}")

    # STEP 11: Add dataset to collection (if requested)
    add_to_collection = dataset_config.get('add_to_collection', False) if dataset_config else False
    collection_id = dataset_config.get('collection_id') if dataset_config else config.DATASETS_COLLECTION_ID

    if config.VERBOSE:
        print(f"[DEBUG] add_to_collection: {add_to_collection}, collection_id: {collection_id}")

    if add_to_collection and collection_id:
        print("\n" + "=" * 60)
        print("STEP 11: ADDING DATASET TO COLLECTION")
        print("=" * 60)
        success = add_dataset_to_collection(syn, dataset_id, collection_id, config.DRY_RUN)
        if success:
            print(f"✓ Dataset added to collection {collection_id}")
    elif add_to_collection and not collection_id:
        print("\n" + "=" * 60)
        print("⚠️  SKIPPING ADD TO COLLECTION")
        print("=" * 60)
        print("⚠️  add_to_collection is enabled but no collection_id provided")
        print("\n💡 To enable, set in config.yaml:")
        print(f"   datasets:")
        print(f"     {args.use_config if hasattr(args, 'use_config') else args.dataset_name}:")
        print(f"       add_to_collection: true")
        print(f"       collection_id: \"synXXXXXX\"  # Or use global datasets_collection_id")

    # STEP 12: Move files to release folder (CONDITIONAL - only if explicitly enabled)
    # This is the FINAL step and should only be done when user is confident
    release_folder = dataset_config.get('release_folder') if dataset_config else (args.release_folder if hasattr(args, 'release_folder') and args.release_folder else None)
    auto_move_to_release = dataset_config.get('auto_move_to_release', False)  # Defaults to False for safety

    if config.VERBOSE:
        print(f"[DEBUG] release_folder: {release_folder}, auto_move_to_release: {auto_move_to_release}")

    if release_folder and auto_move_to_release:
        print("\n" + "=" * 60)
        print("STEP 12: MOVING FILES TO RELEASE FOLDER")
        print("=" * 60)
        print("⚠️  This is a FINAL operation - files will be moved from staging to release")

        # Use folder move mode by default (moves files within folder)
        move_mode = dataset_config.get('move_mode', 'folder')
        success, errors = move_files_to_release(
            syn, args.staging_folder, file_ids, release_folder,
            move_mode, config.DRY_RUN, config.VERBOSE
        )
        print(f"✓ Moved: {success}, Errors: {errors}")
    elif release_folder and not auto_move_to_release:
        print("\n" + "=" * 60)
        print("⏭️  SKIPPING FILE MOVE TO RELEASE")
        print("=" * 60)
        print(f"⚠️  Release folder configured: {release_folder}")
        print(f"⚠️  But auto_move_to_release is set to: {auto_move_to_release}")
        print(f"\n💡 To enable automatic move to release, set in config.yaml:")
        print(f"   datasets:")
        print(f"     {args.use_config if hasattr(args, 'use_config') else args.dataset_name}:")
        print(f"       auto_move_to_release: true")
        print(f"\n⚠️  Files remain in staging folder: {args.staging_folder}")

    # Summary
    print("\n" + "=" * 60)
    print("✅ CREATE WORKFLOW COMPLETE")
    print("=" * 60)
    print(f"Dataset: {args.dataset_name} ({dataset_id})")
    print(f"Files: {len(file_ids)}")
    print(f"Staging Folder: {args.staging_folder}")
    if release_folder and auto_move_to_release:
        print(f"Release Folder: {release_folder} (files moved)")
    elif release_folder:
        print(f"Release Folder: {release_folder} (files NOT moved - set auto_move_to_release: true to enable)")
    if version_label:
        print(f"Version: {version_label}")
    if view_id:
        print(f"Entity View: {view_id}")
    print(f"DRY_RUN: {config.DRY_RUN}")

    if config.DRY_RUN:
        print("\n⚠️  This was a DRY_RUN - no changes made")
        print("Run with --execute to apply changes")


def handle_update_workflow(args, config):
    """Handle UPDATE workflow - update existing dataset with new file versions"""
    print("\n" + "=" * 60)
    print("WORKFLOW: UPDATE EXISTING DATASET")
    print("=" * 60)
    print("This workflow will:")
    print("  1. Retrieve existing annotations from release dataset")
    print("  2. Get new files from staging folder")
    print("  3. Match and merge annotations")
    print("  4. Generate templates for manual editing")
    print("  5. (After editing) Upload new versions to dataset")
    print("\nFor full UPDATE workflow, use all_als_sop.py")
    print("=" * 60)

    # Load schemas
    print("\nLoading schemas...")
    all_schemas = get_all_schemas(config.SCHEMA_BASE_PATH, config.VERBOSE)

    # Connect to Synapse
    print("\nConnecting to Synapse...")
    syn = connect_to_synapse(config)

    # Get dataset name for config lookup
    dataset_name = syn.get(args.dataset_id, downloadFile=False).name
    dataset_config = config.get_dataset_config(dataset_name)
    if dataset_config.get('dataset_type'):
        print(f"Using configured dataset type: {dataset_config['dataset_type']}")

    # Step 1: Retrieve existing annotations
    print("\n" + "=" * 60)
    print("STEP 1: RETRIEVING EXISTING ANNOTATIONS")
    print("=" * 60)

    existing_annotations = enumerate_dataset_files(syn, args.dataset_id, config.VERBOSE)
    print(f"Found {len(existing_annotations)} files in dataset")

    # Step 2: Get staging files (if provided)
    staging_annotations = {}
    if args.staging_folder:
        print("\n" + "=" * 60)
        print("STEP 2: RETRIEVING STAGING FILES")
        print("=" * 60)

        staging_annotations = enumerate_folder_files(syn, args.staging_folder, config.VERBOSE)
        print(f"Found {len(staging_annotations)} files in staging")

    # Step 3: Generate merged templates
    print("\n" + "=" * 60)
    print("STEP 3: GENERATING ANNOTATION TEMPLATES")
    print("=" * 60)

    annotations_output = {}

    # For each existing file, create merged template
    for syn_id, file_data in existing_annotations.items():
        filename = list(file_data.keys())[0]
        old_annot = file_data[filename]

        # Check if there's a staging version
        new_annot = {}
        if syn_id in staging_annotations:
            staging_file_data = staging_annotations[syn_id]
            new_annot = list(staging_file_data.values())[0]

        # Get file type and create template (checks config first, then pattern matching, then defaults to File)
        file_type = old_annot.get('_file_type') or detect_file_type(filename, all_schemas=all_schemas, dataset_config=dataset_config)
        template = create_annotation_template(all_schemas, file_type)

        # Priority merge: old > new > template
        merged = merge_file_annotations_priority(old_annot, new_annot, template)

        annotations_output[syn_id] = {filename: merged}

    # Save annotations (dataset_name retrieved earlier for config lookup)
    output_file = os.path.join(config.ANNOTATIONS_DIR, f"{dataset_name}_update_annotations.json")
    save_annotation_file(annotations_output, output_file)

    print("\n" + "=" * 60)
    print("✅ TEMPLATE GENERATION COMPLETE")
    print("=" * 60)
    print(f"Annotations saved to: {output_file}")
    print(f"Total files: {len(annotations_output)}")
    print("\n⚠️  MANUAL STEP: Edit the annotation file")
    print(f"\nFor full UPDATE workflow with version management, use:")
    print(f"  python all_als_sop.py --from-validation")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Synapse Dataset Manager - Create or update datasets',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # CREATE workflow - using config.yaml settings
  python synapse_dataset_manager.py create --use-config GEN_PIPELINE_TEST

  # CREATE workflow - with manual arguments
  python synapse_dataset_manager.py create \\
    --staging-folder syn12345 \\
    --dataset-name "My New Dataset"

  # CREATE workflow - apply annotations (using config)
  python synapse_dataset_manager.py create --use-config GEN_PIPELINE_TEST \\
    --from-annotations --execute

  # CREATE workflow - apply annotations (manual)
  python synapse_dataset_manager.py create --from-annotations \\
    --staging-folder syn12345 \\
    --dataset-name "My New Dataset" \\
    --execute

  # UPDATE workflow - generate templates
  python synapse_dataset_manager.py update \\
    --dataset-id syn67890 \\
    --staging-folder syn12345

  # Use custom config file
  python synapse_dataset_manager.py --config my-config.yaml create --use-config my_dataset

  # For full UPDATE workflow with versioning, use all_als_sop.py
        """
    )

    # Global options
    parser.add_argument('--config', '-c',
                       help='Path to config file (default: config.yaml)',
                       default=None)

    subparsers = parser.add_subparsers(dest='command', help='Workflow mode')

    # CREATE command
    create_parser = subparsers.add_parser('create', help='Create new dataset from scratch')
    create_parser.add_argument('--use-config',
                              help='Use dataset settings from config.yaml (e.g., "GEN_PIPELINE_TEST")')
    create_parser.add_argument('--staging-folder',
                              help='Synapse ID of staging folder containing files')
    create_parser.add_argument('--dataset-name',
                              help='Name for the new dataset')
    create_parser.add_argument('--from-annotations', action='store_true',
                              help='Skip template generation, use existing annotations')
    create_parser.add_argument('--skip-ai', action='store_true',
                              help='Skip AI-assisted annotation (use Gemini by default)')
    create_parser.add_argument('--execute', action='store_true',
                              help='Execute (override DRY_RUN)')
    create_parser.add_argument('--dry-run', action='store_true',
                              help='Dry run mode')

    # Advanced features
    create_parser.add_argument('--release-folder',
                              help='Move files to release folder after creation (Synapse ID)')
    create_parser.add_argument('--generate-wiki', action='store_true',
                              help='Generate and attach wiki to dataset')
    create_parser.add_argument('--wiki-content',
                              help='Path to custom wiki markdown file (optional)')
    create_parser.add_argument('--create-snapshot', action='store_true',
                              help='Create dataset snapshot/version')
    create_parser.add_argument('--version-label',
                              help='Version label for snapshot and files (e.g., "v1.0")')
    create_parser.add_argument('--version-comment',
                              help='Comment for version/snapshot')
    create_parser.add_argument('--create-entity-view', action='store_true',
                              help='Create entity view for dataset files')

    # UPDATE command
    update_parser = subparsers.add_parser('update', help='Update existing dataset')
    update_parser.add_argument('--dataset-id', required=True,
                              help='Synapse ID of existing dataset')
    update_parser.add_argument('--staging-folder',
                              help='Synapse ID of staging folder with new files (optional)')
    update_parser.add_argument('--execute', action='store_true',
                              help='Execute (override DRY_RUN)')
    update_parser.add_argument('--dry-run', action='store_true',
                              help='Dry run mode')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Load config from file
    config = Config(config_file=args.config)

    # Handle --use-config: Load dataset settings from config
    if args.command == 'create' and hasattr(args, 'use_config') and args.use_config:
        dataset_config = config.get_dataset_config(args.use_config)
        if not dataset_config:
            print(f"❌ Error: Dataset config '{args.use_config}' not found in config file")
            print(f"\nAvailable configs: {list(config.full_config.get('datasets', {}).keys())}")
            sys.exit(1)

        # Load settings from config (only if not provided via CLI)
        if not args.staging_folder and 'staging_folder' in dataset_config:
            args.staging_folder = dataset_config['staging_folder']
            print(f"Using staging_folder from config: {args.staging_folder}")

        if not args.dataset_name and 'dataset_name' in dataset_config:
            args.dataset_name = dataset_config['dataset_name']
            print(f"Using dataset_name from config: {args.dataset_name}")

    # Validate required arguments for create command
    if args.command == 'create':
        if not args.staging_folder:
            print("❌ Error: --staging-folder is required (or use --use-config)")
            sys.exit(1)
        if not args.dataset_name:
            print("❌ Error: --dataset-name is required (or use --use-config)")
            sys.exit(1)

    # Override dry-run from command line
    if hasattr(args, 'execute') and args.execute:
        config.DRY_RUN = False
    if hasattr(args, 'dry_run') and args.dry_run:
        config.DRY_RUN = True

    # Override AI from command line
    if hasattr(args, 'skip_ai') and args.skip_ai:
        config.AI_ENABLED = False

    config.validate()

    # Route to appropriate handler
    if args.command == 'create':
        if args.from_annotations:
            handle_create_from_annotations(args, config)
        else:
            handle_create_workflow(args, config)
    elif args.command == 'update':
        handle_update_workflow(args, config)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
