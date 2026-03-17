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
import string
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


# ==================== DATASET COLUMN SCHEMA FUNCTIONS ====================

def get_dataset_column_schema(dataset_type):
    """
    Get column schema based on dataset type (Clinical or Omic).

    Returns a list of column definitions with size constraints to prevent
    hitting Synapse's 64KB row limit.

    Args:
        dataset_type: String like 'ClinicalDataset', 'OmicDataset', etc.

    Returns:
        List of dicts with keys: name, type, facet, max_size, max_list_len, desc
    """
    # Shared columns for both clinical and omic datasets
    # Note: Set maximum_size and maximum_list_length to stay under 64KB row limit
    shared_columns = [
        {"name": "dataType", "type": ColumnType.STRING, "facet": FacetType.ENUMERATION, "max_size": 100, "desc": "Data type"},
        {"name": "fileFormat", "type": ColumnType.STRING, "facet": FacetType.ENUMERATION, "max_size": 50, "desc": "File format"},
        {"name": "species", "type": ColumnType.STRING, "facet": FacetType.ENUMERATION, "max_size": 100, "desc": "Species"},
        {"name": "disease", "type": ColumnType.STRING, "facet": FacetType.ENUMERATION, "max_size": 100, "desc": "Disease"},
        {"name": "studyType", "type": ColumnType.STRING, "facet": FacetType.ENUMERATION, "max_size": 100, "desc": "Study type"},
        {"name": "dataFormat", "type": ColumnType.STRING_LIST, "facet": FacetType.ENUMERATION, "max_list_len": 10, "desc": "Data format(s)"},
        {"name": "individualCount", "type": ColumnType.STRING_LIST, "facet": FacetType.ENUMERATION, "max_list_len": 10, "desc": "Parrticipant Count"},
        {"name": "url", "type": ColumnType.STRING, "facet": FacetType.ENUMERATION, "max_size": 100, "desc": "URL"},

    ]

    # Clinical-specific columns
    clinical_columns = [
        {"name": "studyPhase", "type": ColumnType.STRING, "facet": FacetType.ENUMERATION, "max_size": 100, "desc": "Phase of study"},
        {"name": "keyMeasures", "type": ColumnType.STRING_LIST, "facet": FacetType.ENUMERATION, "max_list_len": 20, "desc": "Key measurements"},
        {"name": "assessmentType", "type": ColumnType.STRING_LIST, "facet": FacetType.ENUMERATION, "max_list_len": 15, "desc": "Type of assessment"},
        {"name": "clinicalDomain", "type": ColumnType.STRING_LIST, "facet": FacetType.ENUMERATION, "max_list_len": 15, "desc": "Clinical domain"},
        {"name": "hasLongitudinalData", "type": ColumnType.BOOLEAN, "facet": FacetType.ENUMERATION, "desc": "Contains longitudinal data"},
        {"name": "studyDesign", "type": ColumnType.STRING, "facet": FacetType.ENUMERATION, "max_size": 150, "desc": "Study design type"},
        {"name": "primaryOutcome", "type": ColumnType.STRING, "facet": None, "max_size": 250, "desc": "Primary outcome measure"},
    ]

    # Omic-specific columns
    omic_columns = [
        {"name": "assay", "type": ColumnType.STRING_LIST, "facet": FacetType.ENUMERATION, "max_list_len": 10, "desc": "Assay type(s)"},
        {"name": "platform", "type": ColumnType.STRING_LIST, "facet": FacetType.ENUMERATION, "max_list_len": 10, "desc": "Sequencing/analysis platform"},
        {"name": "libraryStrategy", "type": ColumnType.STRING, "facet": FacetType.ENUMERATION, "max_size": 100, "desc": "Library strategy"},
        {"name": "libraryLayout", "type": ColumnType.STRING, "facet": FacetType.ENUMERATION, "max_size": 50, "desc": "Library layout"},
        {"name": "cellType", "type": ColumnType.STRING_LIST, "facet": FacetType.ENUMERATION, "max_list_len": 10, "desc": "Cell type(s)"},
        {"name": "biospecimenType", "type": ColumnType.STRING_LIST, "facet": FacetType.ENUMERATION, "max_list_len": 10, "desc": "Biospecimen type(s)"},
        {"name": "processingLevel", "type": ColumnType.STRING_LIST, "facet": FacetType.ENUMERATION, "max_list_len": 10, "desc": "Data processing level"},
    ]

    # Combine columns based on dataset type
    if dataset_type and 'omic' in dataset_type.lower():
        return shared_columns + omic_columns
    elif dataset_type and 'clinical' in dataset_type.lower():
        return shared_columns + clinical_columns
    else:
        # Default: include both for generic Dataset
        return shared_columns


def get_column_order_template(dataset_type):
    """
    Get ordered list of column names for dataset column reordering.

    Args:
        dataset_type: String like 'ClinicalDataset', 'OmicDataset', etc.

    Returns:
        List of column names in desired order
    """
    # System columns (always first)
    system_columns = ['id', 'name']

    # High-priority shared annotation columns
    shared_priority = ['dataType', 'fileFormat', 'studyType', 'species', 'disease', 'dataFormat']

    # Clinical-specific priority columns
    clinical_priority = [
        'studyPhase', 'assessmentType', 'clinicalDomain', 'keyMeasures',
        'hasLongitudinalData', 'studyDesign', 'primaryOutcome'
    ]

    # Omic-specific priority columns
    omic_priority = [
        'assay', 'platform', 'libraryStrategy', 'libraryLayout',
        'cellType', 'biospecimenType', 'processingLevel'
    ]

    # Standard Synapse metadata columns (always last)
    synapse_columns = [
        'description', 'createdOn', 'createdBy', 'etag', 'modifiedOn', 'modifiedBy',
        'path', 'type', 'currentVersion', 'parentId', 'benefactorId', 'projectId',
        'dataFileHandleId', 'dataFileName', 'dataFileSizeBytes', 'dataFileMD5Hex',
        'dataFileConcreteType', 'dataFileBucket', 'dataFileKey'
    ]

    # Build final order based on dataset type
    if dataset_type and 'omic' in dataset_type.lower():
        return system_columns + shared_priority + omic_priority + synapse_columns
    elif dataset_type and 'clinical' in dataset_type.lower():
        return system_columns + shared_priority + clinical_priority + synapse_columns
    else:
        # Default: shared columns + synapse columns
        return system_columns + shared_priority + synapse_columns


def get_entity_view_column_schema(dataset_type):
    """
    Get column schema for entity views based on dataset type.

    Entity views show the same columns as datasets but apply to Files/Folders.

    Args:
        dataset_type: String like 'ClinicalDataset', 'OmicDataset', etc.

    Returns:
        List of dicts with keys: name, type, facet, max_size, max_list_len, desc
    """
    # Entity views use the same column schema as datasets
    return get_dataset_column_schema(dataset_type)


def get_entity_view_column_order_template(dataset_type):
    """
    Get ordered list of column names for entity view column reordering.

    Entity views use the same order as datasets (id, name first).

    Args:
        dataset_type: String like 'ClinicalDataset', 'OmicDataset', etc.

    Returns:
        List of column names in desired order
    """
    # Entity views use the same column order as datasets
    return get_column_order_template(dataset_type)


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

_NULL_LIKE_VALUES = frozenset({
    'n/a', 'na', 'n/d', 'pen', 'unknown', 'none', 'null', 'nan',
})


def _is_null_like(value) -> bool:
    """Return True if value is a sentinel string that should be treated as empty."""
    if not isinstance(value, str):
        return False
    return value.strip().lower() in _NULL_LIKE_VALUES


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
        if isinstance(value, str) and (value == "" or _is_null_like(value)):
            continue
        if isinstance(value, list):
            value = [v for v in value if not (isinstance(v, str) and _is_null_like(v))]
            if len(value) == 0 or (len(value) == 1 and value[0] == ""):
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

    # Strip blank fields before schema validation — blank means "not filled in", not wrong
    validation_annot = {k: v for k, v in clean_annot.items()
                        if v not in ("", [""], [], None)}

    # Use jsonschema library for proper validation
    try:
        # Create validator
        validator = Draft7Validator(schema)

        # Collect all validation errors
        validation_errors = list(validator.iter_errors(validation_annot))

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
            warnings.append(f"Required field not filled: {field}")

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


def _valid_target(t) -> bool:
    if isinstance(t, str):
        return bool(t.strip())
    if isinstance(t, list):
        return bool(t) and all(isinstance(s, str) and s.strip() for s in t)
    return False


def load_mapping_dict(path) -> dict:
    """Read a JSON-with-comments mapping dict file, return only non-empty-value entries."""
    try:
        with open(path, 'r') as f:
            raw = f.read()
    except FileNotFoundError:
        print(f"❌ Mapping file not found: {path}")
        return {}

    # Strip line-level and inline # comments, but preserve strings
    lines = []
    for line in raw.splitlines():
        # Remove inline comments (not inside strings) — simple heuristic
        stripped = re.sub(r'\s*#[^"]*$', '', line)
        lines.append(stripped)
    cleaned = '\n'.join(lines)

    # Remove trailing commas before } or ] (common in hand-written dicts)
    cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)

    try:
        raw_dict = json.loads(cleaned, strict=False)
    except json.JSONDecodeError as e:
        print(f"⚠ Warning: Could not parse mapping dict {path}: {e}")
        return {}

    # Strip whitespace from keys and keep only non-empty values
    result = {}
    for k, v in raw_dict.items():
        k = k.strip()
        if k == "_views" and isinstance(v, dict):
            result[k] = v  # always carry through view-level annotations
        elif isinstance(v, str) and v.strip():
            result[k] = v
        elif isinstance(v, dict) and _valid_target(v.get('target')):
            result[k] = v
    return result


def load_metadata_file(path) -> list:
    """Load a CSV or XLSX metadata file, returning a list of dicts with whitespace-stripped values."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Metadata file not found: {path}")

    ext = os.path.splitext(path)[1].lower()
    rows = []

    if ext == '.csv':
        with open(path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append({k.strip(): (v.strip() if v else '') for k, v in row.items()})

    elif ext in ('.xlsx', '.xls'):
        try:
            import openpyxl
        except ImportError:
            raise ImportError("openpyxl is required for XLSX support: pip install openpyxl")
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        headers = [str(h).strip() if h is not None else '' for h in next(rows_iter)]
        for row in rows_iter:
            rows.append({headers[i]: (str(v).strip() if v is not None else '') for i, v in enumerate(row)})
        wb.close()

    else:
        raise ValueError(f"Unsupported metadata file extension '{ext}'. Use .csv or .xlsx")

    return rows


def extract_form_name_from_csv(path: str) -> str | None:
    """
    Read a CSV file and return the Form Name value from the first data row.
    Fuzzy-matches the column header: case-insensitive, treats spaces/underscores/hyphens
    as equivalent (so "Form Name", "form_name", "FORM-NAME" all match).
    Returns None if column not found or file is empty.
    """
    import re as _re
    try:
        rows = load_metadata_file(path)
    except Exception:
        return None
    if not rows:
        return None
    # Fuzzy column lookup
    def _norm(s): return _re.sub(r'[\s_\-]+', '', s).lower()
    target = _norm('form name')
    col = next((k for k in rows[0] if _norm(k) == target), None)
    if col is None:
        return None
    return rows[0].get(col, '').strip() or None


def sanitize_synapse_filename(name: str, ext: str = '.csv') -> str:
    """
    Clean a form name into a valid Synapse filename.
    Synapse allows: letters, digits, spaces, _ - . + ' ( )
    Appends ext if no extension is present.
    """
    import re as _re
    name = name.strip()
    name = _re.sub(r"[^\w\s\-\.+'\(\)]", '', name)
    name = name.strip()
    if not os.path.splitext(name)[1]:
        name += ext
    return name


def build_staging_form_map(syn, staging_annotations: dict, download_dir: str) -> tuple[dict, dict, dict, dict]:
    """
    For each staging file, download it and extract the Form Name column value.
    Falls back to the staging filename if no Form Name column is found.

    Returns:
        form_map       — {lower_clean_name: (staging_syn_id, clean_name)}
        name_map       — {staging_syn_id: clean_name}  (human-readable form name)
        local_path_map — {staging_syn_id: local_file_path}  (None if download failed)
        view_map       — {staging_syn_id: view_name}  (raw staging filename w/o extension = view name)
    """
    os.makedirs(download_dir, exist_ok=True)
    form_map = {}
    name_map = {}
    local_path_map = {}
    view_map = {}

    for staging_syn_id, file_data in staging_annotations.items():
        staging_filename = list(file_data.keys())[0]

        local_path = download_file_for_analysis(syn, staging_syn_id, download_dir)
        local_path_map[staging_syn_id] = local_path

        form_name = None
        if local_path and local_path.endswith(('.csv', '.xlsx', '.xls')):
            form_name = extract_form_name_from_csv(local_path)

        if form_name:
            clean = sanitize_synapse_filename(form_name)
        else:
            clean = staging_filename  # fall back to original name

        form_map[_norm_filename_for_match(clean)] = (staging_syn_id, clean)
        name_map[staging_syn_id] = clean
        # Raw staging filename (without extension) IS the view name (e.g. v_ALLALS_AS_ASSEECASCGI)
        view_map[staging_syn_id] = os.path.splitext(staging_filename)[0]

    return form_map, name_map, local_path_map, view_map


def _get_data_dict_views(path: str) -> list:
    """Return all unique View Name values in a data dictionary file."""
    rows = load_metadata_file(path)
    seen = []
    for row in rows:
        v = row.get("View Name", "").strip()
        if v and v not in seen:
            seen.append(v)
    return seen


def _norm_filename_for_match(name: str) -> str:
    """Normalize a filename for fuzzy matching: lowercase and strip hyphens.

    Existing Synapse files omit hyphens (ALSFRSR.csv) while form names retain
    them (ALSFRS-R.csv). Stripping hyphens from both sides aligns them.
    """
    return name.replace('-', '').lower()


# Maps friendly view-filter names to the segment code used in view names
# View names follow the pattern v_ALLALS_{segment}_... (e.g. v_ALLALS_AS_ASSEDEMOG)
_VIEW_SEGMENT_MAP = {
    'assess': 'as',
    'prevent': 'pr',
}


def _view_name_matches(current_view: str, view_name: str) -> bool:
    """Return True if current_view matches the view_name filter.

    Checks segment code first (e.g. 'ASSESS' → 'AS' at index 2 of '_'-split),
    then falls back to exact case-insensitive match.
    """
    vn = view_name.lower()
    cv = current_view.lower()
    code = _VIEW_SEGMENT_MAP.get(vn)
    if code:
        parts = cv.split('_')
        return len(parts) > 2 and parts[2] == code
    return cv == vn


def parse_data_dictionary(path: str, view_name: str = None) -> dict:
    """
    Parse a nested data dictionary CSV/XLSX into a field-info dict.

    Expected columns: View Name, Field, Description, Values
    View Name is sparse — only the first row of each group has a value;
    subsequent rows inherit the last seen View Name (forward-fill).

    Args:
        path: Path to data dictionary CSV or XLSX
        view_name: If provided, only return fields belonging to this View Name

    Returns:
        {field_name: {"description": str, "values": [str, ...]}}
    """
    rows = load_metadata_file(path)

    current_view = ""
    current_field = ""
    result = {}

    for row in rows:
        raw_view = row.get("View Name", "").strip()
        if raw_view:
            current_view = raw_view

        if view_name and not _view_name_matches(current_view, view_name):
            continue

        raw_field = row.get("Field", "").strip()
        description = row.get("Description", "").strip()
        raw_value = row.get("Values", "").strip()

        if raw_field:
            # Field header row — capture field-level description, reset current field
            current_field = raw_field
            if current_field not in result:
                result[current_field] = {"description": description, "view": current_view, "values": {}}
        elif current_field and raw_value:
            # Value row — extract human-readable label from description
            # Description is often "code = label"; strip the leading "code = " prefix
            label = re.sub(r'^\s*\S+\s*=\s*', '', description).strip() if description else raw_value
            result[current_field]["values"][raw_value] = label

    if view_name and not result:
        print(f"  Warning: No fields found for View Name '{view_name}' in {path}")
        available = _get_data_dict_views(path)
        if available:
            print(f"  Available views: {', '.join(available)}")

    return result


def collect_unique_values(paths: list, ignore_cols: set, max_values: int) -> dict:
    """
    Load metadata files and return {col: sorted_unique_values} for columns
    with <= max_values unique values, else {col: None} (no value dict).
    subject_id and anything in ignore_cols is always skipped.
    """
    agg: dict = {}
    for path in paths:
        try:
            rows = load_metadata_file(str(path))
            if not rows:
                continue
            for col in rows[0].keys():
                if col in ignore_cols:
                    continue
                vals = {str(row[col]) for row in rows if row.get(col, "").strip()}
                agg.setdefault(col, set()).update(vals)
            print(f"  loaded {Path(path).name}  ({len(rows)} rows)")
        except Exception as e:
            print(f"  WARNING: skipped {Path(path).name}: {e}")

    result = {}
    for col, vals in agg.items():
        result[col] = sorted(vals) if len(vals) <= max_values else None
    return result


def build_mapping_dict(unique_vals: dict) -> dict:
    """
    Convert {col: sorted_vals | None} into the mapping-dict entry format:
      - list of values  -> {"target": "", "values": {v: "" ...}}
      - None (too many) -> ""
    """
    mapping = {}
    for col, vals in unique_vals.items():
        if vals is None:
            mapping[col] = ""
        else:
            mapping[col] = {"target": "", "values": {v: "" for v in vals}}
    return mapping


def build_mapping_from_data_dict(parsed_dict: dict) -> dict:
    """
    Convert parsed data dictionary into a mapping-dict scaffold.

    Each entry includes:
      - "description": field description from the data dictionary (read-only context
        to help identify which data model attribute this field maps to)
      - "view": the View Name (CRF form) this field belongs to
      - "target": data model field name to map to (empty — user must fill in)
      - "values": {raw_code: human_label} for coded fields, {} for free-text

    Also prepends a "_views" key mapping each unique view name to an empty
    file-level annotation scaffold (assessmentType, clinicalDomain, dataType,
    studyPhase) — fill these in to drive view-level annotation.

    Returns:
        {"_views": {view_name: {file-level annotations}},
         field_name: {"description": str, "view": str, "target": "", "values": {code: label}}}
    """
    views_seen = []
    fields = {}
    for field, info in parsed_dict.items():
        view = info.get("view", "")
        fields[field] = {
            "description": info.get("description", ""),
            "view": view,
            "target": "",
            "values": info.get("values", {}),
        }
        if view and view not in views_seen:
            views_seen.append(view)

    _views = {
        v: {"assessmentType": [], "clinicalDomain": [], "dataType": [], "studyPhase": ""}
        for v in views_seen
    }

    # _views first so it's visible at the top of the file
    result = {"_views": _views}
    result.update(fields)
    return result


def merge_into_existing_mapping(existing_path: str, new_mapping: dict) -> dict:
    """
    Read existing mapping file (raw, preserving empty-value entries), then:
    - Add columns from new_mapping that are absent in existing
    - For existing dict-style entries, add any new values not already present
    - Never overwrite existing mappings
    Returns merged dict.
    """
    with open(existing_path) as f:
        raw = f.read()
    lines = []
    for line in raw.splitlines():
        # Drop pure comment lines (start with optional whitespace then #)
        if re.match(r'^\s*#', line):
            lines.append('')
        else:
            stripped = re.sub(r'\s*#[^"]*$', '', line)
            lines.append(stripped)
    cleaned = re.sub(r',\s*([}\]])', r'\1', '\n'.join(lines))
    existing = json.loads(cleaned, strict=False)

    merged = dict(existing)
    for col, entry in new_mapping.items():
        if col == "_views":
            # Merge view scaffolds: add new views, never overwrite existing
            existing_views = merged.setdefault("_views", {})
            for view_name, scaffold in entry.items():
                if view_name not in existing_views:
                    existing_views[view_name] = scaffold
            continue
        if col not in merged:
            merged[col] = entry
        elif isinstance(merged[col], dict) and isinstance(entry, dict):
            existing_vals = merged[col].get("values", {})
            new_vals = entry.get("values", {})
            for v in new_vals:
                if v not in existing_vals:
                    existing_vals[v] = new_vals[v]  # carry over parsed label
            merged[col]["values"] = existing_vals
            # Carry over view field if missing from existing entry
            if "view" not in merged[col] and "view" in entry:
                merged[col]["view"] = entry["view"]
    return merged


def write_mapping_file(path: str, mapping: dict) -> None:
    header = (
        "# Mapping dict: source_column -> target_data_model_field\n"
        "# Fill in \"target\" with the data model field name for each column.\n"
        "# For value-mapped columns, fill in the data model value for each source value.\n"
        "# Entries with empty string values are ignored during annotation.\n"
    )
    body = json.dumps(mapping, indent=2, ensure_ascii=False)
    with open(path, "w") as f:
        f.write(header + body + "\n")
    print(f"Wrote mapping file: {path}  ({len(mapping)} columns)")


def load_all_metadata_files(paths, join_col='subject_id') -> dict:
    """Load and merge one or more metadata files into a subject_id-keyed index.

    Later files win for overlapping columns. Returns {subject_id: merged_row_dict}.
    """
    index = {}
    for path in paths:
        rows = load_metadata_file(path)
        for row in rows:
            sid = row.get(join_col, '').strip()
            if not sid:
                continue
            if sid in index:
                index[sid].update(row)
            else:
                index[sid] = dict(row)
    return index


def extract_file_extension(file_identifier: str) -> str:
    """
    Extract file extension from filename, URL, or path.

    Args:
        file_identifier: Filename, gs:// URI, or file path

    Returns:
        Lowercase file extension without dot (e.g., 'bam', 'vcf', 'cram')
        Returns empty string if no extension found

    Examples:
        'sample.bam' -> 'bam'
        'gs://bucket/path/file.cram' -> 'cram'
        'data.vcf.gz' -> 'vcf'
        'alignment.bam.bai' -> 'bai'
    """
    if not file_identifier:
        return ''

    # Extract filename from URI/path
    filename = file_identifier.split('/')[-1]

    # Handle no extension
    if '.' not in filename:
        return ''

    # Get all extensions
    parts = filename.split('.')

    # If last extension is compression, use second-to-last
    if len(parts) > 2 and parts[-1].lower() in ['gz', 'bz2', 'zip']:
        return parts[-2].lower()

    # Otherwise use last extension
    return parts[-1].lower()


def map_extension_to_datatype(extension: str) -> str:
    """
    Map file extension to OmicDataTypeEnum value.

    Based on modules/omics/data-types.yaml definitions.

    Args:
        extension: File extension (without dot, lowercase)

    Returns:
        OmicDataTypeEnum value string, or empty string if unmapped

    Note: Index files (bai, crai, tbi, etc.) return empty string as they
          are not omic data types themselves but rather technical indices.
    """
    # Mapping table: extension -> dataType
    extension_map = {
        # Raw sequencing data
        'fastq': 'raw_sequencing',
        'fq': 'raw_sequencing',
        'fasta': 'raw_sequencing',
        'fa': 'raw_sequencing',
        'fna': 'raw_sequencing',

        # Aligned reads
        'bam': 'aligned_reads',
        'sam': 'aligned_reads',
        'cram': 'aligned_reads',

        # Variant calls
        'vcf': 'genomicVariants',
        'bcf': 'genomicVariants',

        # Genome annotation
        'gtf': 'genome_annotation',
        'gff': 'genome_annotation',
        'gff3': 'genome_annotation',
        'bed': 'genome_annotation',

        # Expression data
        'gct': 'gene_expression',

        # Index files - return empty as they are not omic data per se
        # They are technical files for accessing omic data
        'bai': '',
        'crai': '',
        'csi': '',
        'tbi': '',
        'jsi': '',

        # Compressed files - return empty, should use inner extension
        'gz': '',

        # Checksums - not omic data
        'md5': '',
        'md5sum': '',

        # Documentation
        'pdf': '',
        'txt': '',
    }

    return extension_map.get(extension, '')


def map_extension_to_fileformat(extension: str) -> str:
    """
    Map file extension to fileFormat value.

    Args:
        extension: File extension (without dot, lowercase)

    Returns:
        File format string (uppercase), or empty string if unmapped
    """
    # For most formats, uppercase extension is the format
    # Special cases handled explicitly

    format_map = {
        # Sequencing formats
        'fastq': 'FASTQ',
        'fq': 'FASTQ',
        'fasta': 'FASTA',
        'fa': 'FASTA',
        'bam': 'BAM',
        'sam': 'SAM',
        'cram': 'CRAM',

        # Variant formats
        'vcf': 'VCF',
        'bcf': 'BCF',

        # Annotation formats
        'gtf': 'GTF',
        'gff': 'GFF',
        'gff3': 'GFF3',
        'bed': 'BED',

        # Expression formats
        'gct': 'GCT',
        'tsv': 'TSV',
        'csv': 'CSV',

        # Index formats
        'bai': 'BAI',
        'crai': 'CRAI',
        'csi': 'CSI',
        'tbi': 'TBI',
        'jsi': 'JSI',

        # Compressed
        'gz': 'GZIP',

        # Checksums
        'md5': 'MD5',
        'md5sum': 'MD5SUM',

        # Documents
        'pdf': 'PDF',
        'txt': 'TXT',
    }

    return format_map.get(extension, extension.upper() if extension else '')


def extract_file_category(file_identifier: str) -> Optional[str]:
    """
    Detect file category from filename using regex pattern matching.

    Returns category string or None if no match.
    """
    if not file_identifier:
        return None

    filename = file_identifier.split('/')[-1].lower()
    patterns = get_file_category_patterns()

    for category, pattern in patterns.items():
        if re.search(pattern, filename):
            return category

    return None


def get_file_category_patterns() -> Dict[str, str]:
    """Define regex patterns for each file category."""
    return {
        # PDF QC Plots
        'gc_bias_plot': r'gc[_-]?bias',
        'base_distribution_plot': r'base[_-]?distribution[_-]?by[_-]?cycle',
        'insert_size_histogram': r'insert[_-]?size',
        'quality_by_cycle_plot': r'quality[_-]?by[_-]?cycle',
        'quality_distribution_plot': r'quality[_-]?distribution',

        # TXT Files - specific patterns first
        'haplotype_calls': r'haplotype[_-]?calls?',
        'summary_table': r'summary|repeat[_-]?id|repeat[_-]?unit|target[_-]?region|genotype',
    }


def generate_title_from_category(category: str, filename: str = '') -> str:
    """Generate descriptive title based on category and filename."""
    templates = {
        'gc_bias_plot': 'GC Bias QC Plot',
        'base_distribution_plot': 'Base Distribution by Cycle QC Plot',
        'insert_size_histogram': 'Insert Size Histogram',
        'quality_by_cycle_plot': 'Quality by Cycle QC Plot',
        'quality_distribution_plot': 'Quality Distribution QC Plot',
        'haplotype_calls': 'Haplotype Calls',
        'summary_table': 'Repeat Expansion Summary Table',
    }

    base_title = templates.get(category, 'File')

    # Extract subject ID to make title specific
    # First try: subject_XXX or subject-XXX pattern (case insensitive)
    subject_match = re.search(r'(subject[_-]?\d+)', filename, re.IGNORECASE)
    if subject_match:
        return f"{base_title} - {subject_match.group(1)}"

    # Second try: alphanumeric IDs like ABCD1234 (must be 6+ chars with both letters and numbers)
    # Match IDs that start at word boundary or beginning of string
    subject_match = re.search(r'(?:^|/)([A-Za-z]+\d+[A-Za-z\d]*|[A-Za-z\d]*\d+[A-Za-z]+)(?:[_\-/\.]|$)', filename)
    if subject_match:
        match_text = subject_match.group(1)
        # Filter out common false positives and ensure minimum length
        if len(match_text) >= 6 and match_text.lower() not in ['bucket', 'subject']:
            return f"{base_title} - {match_text}"

    return base_title


def generate_description_from_category(category: str) -> str:
    """Generate description text (max 500 chars)."""
    descriptions = {
        'gc_bias_plot': 'Quality control plot showing GC content bias across the sequence, '
                       'used to assess systematic biases in sequencing coverage related to GC content.',
        'base_distribution_plot': 'Quality control plot displaying the distribution of nucleotide bases '
                                 '(A, T, G, C) across sequencing cycles, useful for detecting sequence composition bias.',
        'insert_size_histogram': 'Distribution plot of DNA fragment insert sizes in the sequencing library, '
                                'important for validating library preparation and identifying size selection issues.',
        'quality_by_cycle_plot': 'Quality control plot showing sequencing quality scores across base positions, '
                                'used to identify quality degradation patterns during sequencing runs.',
        'quality_distribution_plot': 'Distribution of sequencing quality scores across all reads, '
                                    'provides an overview of overall sequencing quality.',
        'haplotype_calls': 'Variant haplotype calls from whole genome sequencing, '
                          'containing phased genomic variant information. May include companion index files (.tbi).',
        'summary_table': 'Summary table containing repeat expansion analysis results including repeat ID, '
                        'repeat unit sequences, target genomic regions, and genotype information.',
    }
    return descriptions.get(category, '')


def generate_keywords_from_category(category: str) -> List[str]:
    """Generate keyword list based on category."""
    keyword_map = {
        'gc_bias_plot': ['qc', 'quality_control', 'gc_bias', 'sequencing_qc', 'plot'],
        'base_distribution_plot': ['qc', 'quality_control', 'base_distribution', 'sequencing_qc', 'plot'],
        'insert_size_histogram': ['qc', 'quality_control', 'insert_size', 'library_qc', 'histogram'],
        'quality_by_cycle_plot': ['qc', 'quality_control', 'quality_score', 'sequencing_qc', 'plot'],
        'quality_distribution_plot': ['qc', 'quality_control', 'quality_score', 'sequencing_qc', 'plot'],
        'haplotype_calls': ['variant_calls', 'haplotype', 'genomics', 'vcf', 'phased_variants'],
        'summary_table': ['repeat_expansion', 'summary', 'genotype', 'genomics', 'c9orf72', 'atxn2'],
    }
    return keyword_map.get(category, [])


def get_datatype_from_category(category: str) -> Optional[str]:
    """Map category to OmicDataTypeEnum value."""
    datatype_map = {
        'haplotype_calls': 'variant_calls',
        'summary_table': 'genomicVariants',
        # QC plots don't have specific dataType (they're QC files, not primary data)
    }
    return datatype_map.get(category)


def extract_variant_type_from_path(folder_path: str) -> Optional[str]:
    """
    Detect variant type from folder path structure.

    Args:
        folder_path: Folder path (e.g., "wgs/vcf/structural/SUBJECT001")

    Returns:
        Internal variant type identifier or None

    Examples:
        >>> extract_variant_type_from_path("wgs/vcf/structural/SUBJECT001")
        'structural'
        >>> extract_variant_type_from_path("wgs/vcf/small/SUBJECT001")
        'small'
        >>> extract_variant_type_from_path("wgs/vcf/genomic/SUBJECT001")
        'genomic'
        >>> extract_variant_type_from_path("wgs/vcf/repeat-expansion/SUBJECT001")
        'repeat_expansion'
    """
    if not folder_path:
        return None

    path_lower = folder_path.lower()
    path_parts = [p.strip() for p in path_lower.split('/') if p.strip()]

    # Priority order: more specific patterns first
    if 'repeat-expansion' in path_parts or 'repeat_expansion' in path_parts:
        return 'repeat_expansion'
    elif 'structural' in path_parts:
        return 'structural'
    elif 'small' in path_parts:
        return 'small'
    elif 'genomic' in path_parts:
        return 'genomic'

    return None


def map_variant_type_to_enum(variant_type: str) -> Optional[str]:
    """
    Map internal variant type to VariantTypeEnum value.

    Args:
        variant_type: Internal variant type identifier

    Returns:
        VariantTypeEnum value or None

    Examples:
        >>> map_variant_type_to_enum('structural')
        'Structural_Variant'
        >>> map_variant_type_to_enum('small')
        'Small_Variant'
    """
    if not variant_type:
        return None

    variant_type_map = {
        'structural': 'Structural_Variant',
        'repeat_expansion': 'Repeat_Expansion',
        'small': 'Small_Variant',
        'genomic': 'Genomic',
    }

    return variant_type_map.get(variant_type)


def map_variant_type_to_datatype(variant_type: str) -> Optional[str]:
    """
    Map variant type to specific OmicDataTypeEnum value.

    Args:
        variant_type: Internal variant type identifier

    Returns:
        OmicDataTypeEnum value or None

    Examples:
        >>> map_variant_type_to_datatype('structural')
        'StructuralVariants'
        >>> map_variant_type_to_datatype('small')
        'GermlineVariants'
    """
    if not variant_type:
        return None

    datatype_map = {
        'structural': 'StructuralVariants',
        'repeat_expansion': 'genomicVariants',
        'small': 'GermlineVariants',
        'genomic': 'genomicVariants',
    }

    return datatype_map.get(variant_type)


def generate_variant_type_keywords(variant_type: str) -> List[str]:
    """
    Generate keywords based on variant type.

    Args:
        variant_type: Internal variant type identifier

    Returns:
        List of keywords for search and filtering

    Examples:
        >>> generate_variant_type_keywords('structural')
        ['structural_variants', 'cnv', 'copy_number', 'deletions', 'duplications', 'genomics', 'vcf']
        >>> generate_variant_type_keywords('small')
        ['small_variants', 'snv', 'indel', 'germline', 'genomics', 'vcf']
    """
    if not variant_type:
        return []

    keyword_map = {
        'structural': ['structural_variants', 'cnv', 'copy_number', 'deletions', 'duplications', 'genomics', 'vcf'],
        'repeat_expansion': ['repeat_expansion', 'c9orf72', 'atxn2', 'repeat_analysis', 'genomics', 'vcf'],
        'small': ['small_variants', 'snv', 'indel', 'germline', 'genomics', 'vcf'],
        'genomic': ['genomic_variants', 'haplotype', 'variant_calls', 'genomics', 'vcf'],
    }

    return keyword_map.get(variant_type, [])


def enrich_metadata_with_file_info(metadata_row: dict, file_name: str = None, folder_path: str = None) -> dict:
    """
    Enrich metadata row with computed fields derived from file name/URI.

    Adds computed columns:
    - _file_extension: Extracted file extension
    - _computed_dataType: Data type derived from extension
    - _computed_fileFormat: File format derived from extension
    - _file_category: Category detected from filename pattern (NEW)
    - _computed_title: Generated title based on category (NEW)
    - _computed_description: Generated description based on category (NEW)
    - _computed_keywords: Generated keywords based on category (NEW)
    - _computed_variantType: Variant type for VCF files (NEW)
    - _variant_type_detected: Internal variant type identifier (NEW, debug)

    Args:
        metadata_row: Original metadata dictionary
        file_name: Optional file name to use for enrichment.
                   IMPORTANT: If provided, this takes PRIORITY over any
                   file paths in metadata_row to avoid using stale/polluted
                   values from metadata merging.
        folder_path: Optional folder path for variant type detection.
                     Used to extract variant type from folder structure
                     (e.g., "wgs/vcf/structural/SUBJECT001").
                     IMPORTANT: If provided, takes PRIORITY over any
                     folder paths in metadata_row.

    Returns:
        Enriched metadata dictionary with computed fields
    """
    enriched = metadata_row.copy()

    # Determine file identifier source (priority order)
    # CRITICAL: Prioritize explicit file_name parameter over metadata columns
    # to avoid using stale/polluted gs_uri values from metadata merging
    file_identifier = None

    # First: Use explicit file_name parameter if provided
    if file_name:
        file_identifier = file_name
    # Second: Fall back to metadata columns
    else:
        for col in ['gs_uri', 'url', 'file_name', 'filename', 'name']:
            if col in enriched and enriched[col]:
                file_identifier = enriched[col]
                break

    if not file_identifier:
        return enriched

    # Extract extension
    extension = extract_file_extension(file_identifier)
    enriched['_file_extension'] = extension

    # Map to dataType
    data_type = map_extension_to_datatype(extension)
    if data_type:
        enriched['_computed_dataType'] = data_type

    # Map to fileFormat
    file_format = map_extension_to_fileformat(extension)
    if file_format:
        enriched['_computed_fileFormat'] = file_format

    # NEW: Category-based enrichment for PDF and TXT files
    if extension in ['pdf', 'txt']:
        category = extract_file_category(file_identifier)

        if category:
            enriched['_file_category'] = category

            # Generate title
            title = generate_title_from_category(category, file_identifier)
            if title:
                enriched['_computed_title'] = title

            # Generate description
            description = generate_description_from_category(category)
            if description:
                enriched['_computed_description'] = description

            # Generate keywords
            keywords = generate_keywords_from_category(category)
            if keywords:
                enriched['_computed_keywords'] = keywords

            # Override dataType for specific TXT categories
            category_datatype = get_datatype_from_category(category)
            if category_datatype:
                enriched['_computed_dataType'] = category_datatype

    # VCF Variant Type Detection from folder structure
    if extension == 'vcf' and folder_path:
        variant_type = extract_variant_type_from_path(folder_path)

        if variant_type:
            # Store internal identifier for debugging
            enriched['_variant_type_detected'] = variant_type

            # Map to VariantTypeEnum value
            variant_enum = map_variant_type_to_enum(variant_type)
            if variant_enum:
                enriched['_computed_variantType'] = variant_enum

            # Override dataType with specific value
            specific_datatype = map_variant_type_to_datatype(variant_type)
            if specific_datatype:
                enriched['_computed_dataType'] = specific_datatype

            # Generate variant-type keywords
            variant_keywords = generate_variant_type_keywords(variant_type)
            if variant_keywords:
                enriched['_computed_keywords'] = variant_keywords

    return enriched


def _coerce_numeric(value):
    """Coerce a string value to int or float if possible, else return as-is."""
    if not isinstance(value, str):
        return value
    try:
        return int(value)
    except (ValueError, TypeError):
        pass
    try:
        return float(value)
    except (ValueError, TypeError):
        pass
    return value


def fill_template_from_metadata(template, metadata_row, mapping) -> dict:
    """Fill empty template slots from a metadata row using the field mapping.

    Only writes to fields that are currently empty; does not overwrite existing values.
    """
    result = dict(template)

    # Pass 1: fill fields from metadata or constants (skip value_template entries)
    for source_col, mapping_entry in mapping.items():
        if isinstance(mapping_entry, dict) and 'value_template' in mapping_entry:
            continue  # defer to pass 2

        if isinstance(mapping_entry, dict):
            raw_target = mapping_entry['target']
            value_map  = mapping_entry.get('values', {})
            constant   = mapping_entry.get('value')
        else:
            raw_target = mapping_entry
            value_map  = {}
            constant   = None

        target_fields = raw_target if isinstance(raw_target, list) else [raw_target]

        # Hard-coded constant bypasses metadata lookup entirely
        if constant is not None:
            value = constant
        else:
            value = metadata_row.get(source_col, '')
            if not value:
                continue
            if _is_null_like(value):
                continue
            if value_map:
                value = value_map.get(value, value) or value
                if _is_null_like(value):
                    continue

        for target_field in target_fields:
            # Coerce string → int/float for numeric schema fields
            if target_field in result and result[target_field] is None:
                value = _coerce_numeric(value)

            current = result.get(target_field)
            additions = value if isinstance(value, list) else [value]

            if isinstance(current, list):
                # Append any new values not already present (covers keywords too)
                existing = [x for x in current if x not in ('', None)]
                new_items = [v for v in additions if v and v not in existing]
                if new_items:
                    result[target_field] = existing + new_items
            elif current in ('', None):
                # Scalar field that is empty — fill it
                result[target_field] = value
            else:
                # Non-list field already has a value — leave it
                pass

    # Pass 2: fill value_template entries using already-populated fields
    for source_col, mapping_entry in mapping.items():
        if not (isinstance(mapping_entry, dict) and 'value_template' in mapping_entry):
            continue

        raw_target     = mapping_entry['target']
        target_fields  = raw_target if isinstance(raw_target, list) else [raw_target]
        value_template = mapping_entry['value_template']

        # Flatten single-element lists to scalars for interpolation
        flat = {
            k: (v[0] if isinstance(v, list) and len(v) == 1 else v)
            for k, v in result.items()
        }

        # Extract referenced field names from template
        referenced_fields = [fn for _, fn, _, _ in string.Formatter().parse(value_template) if fn]

        # Skip if any referenced field is missing or empty
        if any(not flat.get(f) for f in referenced_fields):
            continue

        try:
            rendered_value = value_template.format_map(flat)
        except KeyError:
            continue

        for target_field in target_fields:
            if result.get(target_field) in ('', None, ['']):
                result[target_field] = rendered_value

    return result


def fill_template_from_file_contents(template: dict, file_path: str, mapping: dict) -> dict:
    """Fill annotation template fields by reading a multi-subject data file and
    collecting unique values per mapped column across all rows.

    For each source_col in mapping that exists as a column in the file:
      - Collect all unique non-null values in that column
      - Translate each via the mapping dict's values map
      - Merge translated values into the target annotation field as a list

    Only fills empty or partially-empty template slots; does not overwrite
    already-populated values unless they are blank/null.

    Args:
        template:  Annotation template dict to fill
        file_path: Path to the data CSV/XLSX file
        mapping:   Mapping dict loaded via load_mapping_dict()

    Returns:
        Updated template dict
    """
    try:
        rows = load_metadata_file(file_path)
    except Exception as e:
        print(f"  ⚠️  Could not load {file_path} for annotation filling: {e}")
        return template

    if not rows:
        return template

    result = dict(template)
    available_cols = set(rows[0].keys())

    for source_col, mapping_entry in mapping.items():
        if source_col not in available_cols:
            continue

        if isinstance(mapping_entry, dict):
            raw_target = mapping_entry.get('target', '')
            value_map  = mapping_entry.get('values', {})
        else:
            raw_target = mapping_entry
            value_map  = {}

        if not raw_target:
            continue

        target_fields = raw_target if isinstance(raw_target, list) else [raw_target]

        # Collect unique non-null raw values across all rows
        raw_values_seen = []
        for row in rows:
            v = str(row.get(source_col, '') or '').strip()
            if v and not _is_null_like(v) and v not in raw_values_seen:
                raw_values_seen.append(v)

        if not raw_values_seen:
            continue

        # Translate via value map; keep untranslated values as-is if no map entry
        translated = []
        for v in raw_values_seen:
            mapped_v = value_map.get(v, v) if value_map else v
            if mapped_v and not _is_null_like(mapped_v) and mapped_v not in translated:
                translated.append(mapped_v)

        if not translated:
            continue

        for target_field in target_fields:
            current = result.get(target_field)

            if isinstance(current, list):
                # Merge into existing list, skip blanks
                existing = [x for x in current if x not in ('', None)]
                merged = existing[:]
                for v in translated:
                    if v not in merged:
                        merged.append(v)
                if merged:
                    result[target_field] = merged
            elif current in ('', None):
                # Scalar field — store as list if multiple values, scalar if one
                result[target_field] = translated if len(translated) > 1 else translated[0]

    return result


def infer_view_from_columns(file_path: str, mapping: dict) -> str | None:
    """Infer the _views key for a file by checking which view appears most in its columns.

    Each mapping entry carries a "view" field (the source database view name).
    By tallying how many of the file's columns belong to each view, we identify
    the dominant view and return it so apply_view_annotations can match it.

    Returns None if the file cannot be read or no mapping entries have a view field.
    """
    try:
        rows = load_metadata_file(file_path)
    except Exception:
        return None
    if not rows:
        return None
    columns = set(rows[0].keys())
    view_counts: dict[str, int] = {}
    for col in columns:
        entry = mapping.get(col)
        if isinstance(entry, dict) and entry.get('view'):
            v = entry['view']
            view_counts[v] = view_counts.get(v, 0) + 1
    if not view_counts:
        return None
    return max(view_counts, key=view_counts.get)


def apply_view_annotations(template: dict, form_name: str, mapping: dict) -> dict:
    """Apply view-level file annotations from the _views section of a mapping dict.

    The mapping dict's "_views" key maps each CRF form/view name to a dict of
    file-level annotation fields (assessmentType, clinicalDomain, dataType,
    studyPhase, etc.) that should apply to any file extracted from that view.

    Matching is case-insensitive with hyphens/underscores/spaces normalised.

    Args:
        template:  Annotation template dict to fill
        form_name: The form/view name of the staging file (from extract_form_name_from_csv)
        mapping:   Mapping dict loaded via load_mapping_dict() — must contain "_views"

    Returns:
        Updated template dict (only empty slots are filled)
    """
    views = mapping.get("_views", {})
    if not views or not form_name:
        return template

    def _norm(s):
        return re.sub(r'[\s_\-]+', '', s).lower()

    form_norm = _norm(form_name)
    matched_view = next((v for v in views if _norm(v) == form_norm), None)
    if not matched_view:
        return template

    result = dict(template)
    for field, value in views[matched_view].items():
        if not value:
            continue
        current = result.get(field)
        if isinstance(current, list):
            existing = [x for x in current if x not in ('', None)]
            additions = value if isinstance(value, list) else [value]
            for v in additions:
                if v and v not in existing:
                    existing.append(v)
            if existing:
                result[field] = existing
        elif current in ('', None):
            result[field] = value

    return result


def detect_subject_file_type(file_path: str, subject_id_col: str = None) -> str:
    """Detect whether a data file contains a single subject or multiple subjects.

    Detection order:
    1. Extension heuristic — genomics/sequencing formats are always single-subject;
       tabular formats proceed to content inspection.
    2. Content inspection — count unique values in the subject identifier column.

    Args:
        file_path:       Path to (or name of) the file being evaluated
        subject_id_col:  Column name that holds subject IDs (e.g. "SubjectUID").
                         Falls back to common names if None or not found.

    Returns:
        'single' or 'multi'
    """
    # File extensions that are unambiguously single-subject (genomics / sequencing)
    _SINGLE_SUBJECT_EXTS = {
        '.fastq', '.fq', '.bam', '.cram', '.sam',
        '.vcf', '.bcf', '.gvcf',
        '.tbi', '.bai', '.crai', '.csi',
        '.bed', '.bedgraph', '.bigwig', '.bw', '.wig', '.bigbed',
        '.fasta', '.fa', '.fastq.gz', '.fq.gz', '.vcf.gz', '.bcf.gz', '.gvcf.gz',
    }

    # File extensions that are tabular and likely multi-subject
    _TABULAR_EXTS = {
        '.csv', '.tsv', '.txt', '.xlsx', '.xls', '.parquet', '.feather',
    }

    _COMMON_SUBJECT_COLS = ['SubjectUID', 'subject_id', 'subjectId', 'SubjectId',
                            'GUID', 'ParticipantID', 'participant_id']

    # Normalise: strip query strings, lowercased suffix
    name = os.path.basename(file_path).lower()

    # Handle compound extensions (.fastq.gz, .vcf.gz, etc.)
    for ext in _SINGLE_SUBJECT_EXTS:
        if name.endswith(ext):
            return 'single'

    # For non-tabular, non-genomics formats (images, PDFs, etc.) default to single
    is_tabular = any(name.endswith(ext) for ext in _TABULAR_EXTS)
    if not is_tabular:
        return 'single'

    # Tabular file — inspect contents
    try:
        rows = load_metadata_file(file_path)
    except Exception:
        return 'multi'  # safe default if we can't read it

    if not rows:
        return 'single'

    available = set(rows[0].keys())

    # Build candidate list: explicit col first, then common fallbacks
    candidates = []
    if subject_id_col:
        candidates.append(subject_id_col)
    candidates.extend(c for c in _COMMON_SUBJECT_COLS if c not in candidates)

    for col in candidates:
        if col not in available:
            continue
        unique_ids = {str(row.get(col, '') or '').strip() for row in rows}
        unique_ids.discard('')
        return 'single' if len(unique_ids) <= 1 else 'multi'

    # No subject column found — treat as multi if more than one row
    return 'single' if len(rows) <= 1 else 'multi'


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


def normalize_annotations_from_mapping(annotations: dict, mapping: dict) -> dict:
    """
    Normalize existing annotation values in-place using a mapping dict.

    Unlike fill_template_from_metadata (which pulls values from a separate metadata row),
    this function looks up values that already exist in the annotations and translates
    them through the mapping's value map.

    Only modifies fields that:
      - exist in the mapping (via their target field name)
      - already have a non-empty value in the annotations
      - have an explicit translation in the values dict

    Does NOT add new fields or overwrite values not present in the value map.

    Args:
        annotations: Current annotation dict (data-model field names → values)
        mapping: Mapping dict {source_col: {"target": field, "values": {src: tgt}} | str}

    Returns:
        New dict with normalized values.
    """
    result = dict(annotations)

    for _source_col, entry in mapping.items():
        if isinstance(entry, dict):
            raw_target = entry.get('target', '')
            value_map = entry.get('values', {})
        elif isinstance(entry, str) and entry.strip():
            raw_target = entry
            value_map = {}
        else:
            continue

        if not raw_target or not value_map:
            continue

        targets = raw_target if isinstance(raw_target, list) else [raw_target]
        for t in targets:
            current = result.get(t)
            if current is None or current == '' or current == [] or current == ['']:
                continue
            if isinstance(current, list):
                result[t] = [value_map.get(str(v), v) for v in current]
            else:
                result[t] = value_map.get(str(current), current)

    return result


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


def apply_annotations_to_files(syn, file_annotations_dict, dry_run=True, verbose=False,
                                version_label=None, version_comment=None):
    """
    Apply annotations to file entities in Synapse.
    Used in CREATE workflow and UPDATE workflow (annotation-only path).

    If version_label is provided, a new version is forced so the label is applied.
    """
    success_count = 0
    error_count = 0

    for syn_id, file_data in file_annotations_dict.items():
        filename = list(file_data.keys())[0]
        annotations = file_data[filename]

        try:
            cleaned = clean_annotations_for_synapse(annotations)

            if dry_run:
                label_str = f" with label '{version_label}'" if version_label else ""
                print(f"  [DRY_RUN] Would apply {len(cleaned)} annotations to {filename}{label_str}")
                success_count += 1
            else:
                entity = syn.get(syn_id, downloadFile=False)
                entity.annotations = cleaned
                if version_comment:
                    entity['versionComment'] = version_comment
                syn.store(entity, forceVersion=bool(version_label),
                          versionLabel=version_label or None)

                if verbose:
                    print(f"  ✓ Applied annotations to {filename}")
                success_count += 1

        except Exception as e:
            err_str = str(e)
            if 'UNIQUE_REVISION_LABEL' in err_str or 'Duplicate entry' in err_str:
                print(f"  [SKIP] Version '{version_label}' already exists for {filename} ({syn_id}) — skipping")
                success_count += 1
            else:
                print(f"  ✗ Error applying annotations to {filename}: {e}")
                error_count += 1

    return success_count, error_count


def apply_dataset_annotations(syn, dataset_syn_id, annotations, all_schemas, dry_run=True):
    """
    Apply annotations to an existing dataset entity in Synapse.

    Args:
        syn: Synapse client
        dataset_syn_id: Synapse ID of the existing dataset entity
        annotations: Dict of annotations to apply
        all_schemas: Dict of loaded JSON schemas (for validation)
        dry_run: If True, only show what would be done

    Returns:
        bool: True if successful, False otherwise
    """
    dataset_type = annotations.get('_dataset_type', 'ClinicalDataset')

    is_valid, errors, warnings = validate_annotation_against_schema(
        annotations, dataset_type, all_schemas
    )

    if warnings:
        print(f"  Warnings ({len(warnings)}):")
        for w in warnings:
            print(f"    ⚠️  {w}")

    if not is_valid:
        print(f"  Errors ({len(errors)}):")
        for e in errors:
            print(f"    ✗ {e}")
        print("  ❌ Validation failed — annotations not applied")
        return False

    cleaned = clean_annotations_for_synapse(annotations)

    if dry_run:
        print(f"  [DRY_RUN] Would apply {len(cleaned)} annotations to {dataset_syn_id}")
        print(f"  [DRY_RUN] Fields: {', '.join(list(cleaned.keys())[:10])}{'...' if len(cleaned) > 10 else ''}")
        return True

    try:
        entity = syn.get(dataset_syn_id, downloadFile=False)
        entity.annotations = cleaned
        syn.store(entity)
        print(f"  ✓ Applied {len(cleaned)} annotations to {dataset_syn_id}")
        return True
    except Exception as e:
        print(f"  ✗ Error applying annotations: {e}")
        return False


def validate_link_dataset_annotations(dataset_annotations):
    """
    Validate that link dataset has required url field.

    Args:
        dataset_annotations: Dataset annotation dict

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not dataset_annotations.get('url'):
        return False, "Missing required 'url' field - link datasets must reference an external URL"

    url_value = dataset_annotations.get('url', '').strip()
    if url_value == '':
        return False, "Empty 'url' field - link datasets must have a valid external URL"

    return True, None


def create_dataset_entity(syn, dataset_name, dataset_annotations, project_id,
                         all_schemas, dry_run=True, description=None):
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
            if cleaned:
                print(f"  [DRY_RUN] Annotations: {', '.join(list(cleaned.keys())[:10])}")
            if description:
                print(f"  [DRY_RUN] Description: {description[:80]}{'...' if len(description) > 80 else ''}")
            return "syn_DRYRUN_DATASET"

        # Create dataset (without annotations first)
        dataset = Dataset(
            name=dataset_name,
            parent_id=project_id
        )
        dataset = dataset.store()
        print(f"  ✓ Created dataset: {dataset.id}")

        # Apply annotations and description using the old API (get, set, store)
        # The new Dataset models API doesn't properly persist annotations
        entity = syn.get(dataset.id, downloadFile=False)
        if cleaned:
            try:
                entity.annotations = cleaned
                if description:
                    entity.description = description
                syn.store(entity)
                print(f"  ✓ Applied {len(cleaned)} annotations: {', '.join(list(cleaned.keys())[:10])}")
                if description:
                    print(f"  ✓ Set description")
            except Exception as e:
                print(f"  ⚠️  Warning: Failed to apply annotations: {e}")
                import traceback
                traceback.print_exc()
        elif description:
            try:
                entity.description = description
                syn.store(entity)
                print(f"  ✓ Set description")
            except Exception as e:
                print(f"  ⚠️  Warning: Failed to set description: {e}")
        else:
            print(f"  ⚠️  Warning: No annotations to apply")

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


def add_dataset_columns(syn, dataset_id, all_schemas, file_type='ClinicalFile',
                       dataset_type=None, extra_columns=None, dry_run=True):
    """
    Add annotation columns to dataset for faceted search with size constraints.

    Args:
        syn: Synapse client
        dataset_id: Dataset Synapse ID
        all_schemas: Dict of all loaded schemas (kept for backward compatibility)
        file_type: File type (kept for backward compatibility)
        dataset_type: Dataset type ('ClinicalDataset', 'OmicDataset', etc.)
                     If not provided, will auto-detect from dataset annotations
        extra_columns: Optional list of extra column name strings to add (from config)
        dry_run: If True, only print what would be done

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Auto-detect dataset type from annotations if not provided
        if not dataset_type:
            dataset = Dataset(dataset_id).get()
            annotations = dataset.annotations if hasattr(dataset, 'annotations') else {}
            dataset_type = annotations.get('_dataset_type', 'ClinicalDataset')
            if hasattr(dataset, 'annotations'):
                print(f"  📊 Auto-detected dataset type: {dataset_type}")

        # Get column schema for this dataset type
        columns_to_add = get_dataset_column_schema(dataset_type)

        if dry_run:
            print(f"  [DRY_RUN] Would add {len(columns_to_add)} columns to dataset ({dataset_type})")
            print(f"  [DRY_RUN] Columns: {', '.join([c['name'] for c in columns_to_add])}")
            if extra_columns:
                print(f"  [DRY_RUN] Extra columns from config: {', '.join(extra_columns)}")
            return True

        # Get dataset with existing columns
        dataset = Dataset(dataset_id).get()

        # Get existing columns to avoid duplicates
        existing_columns = []
        if hasattr(dataset, 'columns_to_store') and dataset.columns_to_store:
            existing_columns = [col.name for col in dataset.columns_to_store]

        # Add columns with size constraints
        added_count = 0
        for col_info in columns_to_add:
            if col_info['name'] not in existing_columns:
                try:
                    # Build column kwargs
                    col_kwargs = {
                        'name': col_info['name'],
                        'column_type': col_info['type'],
                        'facet_type': col_info.get('facet')
                    }

                    # Add size constraints to prevent 64KB row limit violations
                    if col_info['type'] == ColumnType.STRING and 'max_size' in col_info:
                        col_kwargs['maximum_size'] = col_info['max_size']
                    elif col_info['type'] == ColumnType.STRING_LIST and 'max_list_len' in col_info:
                        col_kwargs['maximum_list_length'] = col_info['max_list_len']

                    col = Column(**col_kwargs)
                    dataset.add_column(column=col)
                    added_count += 1
                except Exception as e:
                    print(f"    ⚠️  Could not add column {col_info['name']}: {e}")
            else:
                print(f"    ℹ️  Column {col_info['name']} already exists, skipping")

        # Add extra columns from config (annotation-derived)
        for col_name in (extra_columns or []):
            if col_name not in existing_columns:
                try:
                    col = Column(
                        name=col_name,
                        column_type=ColumnType.STRING,
                        facet_type=FacetType.ENUMERATION,
                        maximum_size=250
                    )
                    dataset.add_column(column=col)
                    added_count += 1
                except Exception as e:
                    print(f"    ⚠️  Could not add extra column {col_name}: {e}")
            else:
                print(f"    ℹ️  Column {col_name} already exists, skipping")

        # Store changes
        if added_count > 0:
            dataset.store()
            print(f"  ✓ Added {added_count} columns to dataset ({dataset_type})")
        else:
            print(f"  ℹ️  No new columns to add (all {len(columns_to_add)} already exist)")

        return True

    except Exception as e:
        print(f"  ✗ Error adding columns: {e}")
        import traceback
        traceback.print_exc()
        return False


def reorder_dataset_columns(syn, dataset_id, dataset_type=None, dry_run=True):
    """
    Reorder dataset columns based on priority template.

    Puts important columns first for better UX in Synapse UI:
    1. System columns (id, name)
    2. High-priority annotation columns (dataType, fileFormat, etc.)
    3. Type-specific columns (clinical or omic)
    4. Standard Synapse metadata columns

    Args:
        syn: Synapse client
        dataset_id: Dataset Synapse ID
        dataset_type: Dataset type ('ClinicalDataset', 'OmicDataset', etc.)
                     If not provided, will auto-detect from dataset annotations
        dry_run: If True, only print what would be done

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Auto-detect dataset type if not provided
        if not dataset_type:
            dataset = Dataset(dataset_id).get()
            annotations = dataset.annotations if hasattr(dataset, 'annotations') else {}
            dataset_type = annotations.get('_dataset_type', 'ClinicalDataset')

        # Get dataset with columns (matching notebook pattern)
        dataset = Dataset(id=dataset_id).get(include_columns=True)

        # Get current column order (using dataset.columns.keys() like the notebook)
        if not hasattr(dataset, 'columns') or not dataset.columns:
            print(f"  ℹ️  No columns to reorder")
            return True

        current_columns = list(dataset.columns.keys())

        # Build ordered list from template
        template_order = get_column_order_template(dataset_type)

        # Filter template to only include columns that exist in dataset
        final_order = []
        for col in template_order:
            if col in current_columns:
                final_order.append(col)

        # Append any remaining columns not in template (to handle custom columns)
        remaining_cols = [col for col in current_columns if col not in final_order]
        final_order.extend(remaining_cols)

        if dry_run:
            print(f"  [DRY_RUN] Would reorder {len(final_order)} columns")
            print(f"  [DRY_RUN] Current order: {', '.join(current_columns[:10])}{'...' if len(current_columns) > 10 else ''}")
            print(f"  [DRY_RUN] New order: {', '.join(final_order[:10])}{'...' if len(final_order) > 10 else ''}")
            return True

        # Apply reordering (matching notebook pattern)
        for target_index, col_name in enumerate(final_order):
            dataset.reorder_column(name=col_name, index=target_index)

        # Store changes
        dataset.store()
        print(f"  ✓ Reordered {len(final_order)} columns ({dataset_type})")

        return True

    except Exception as e:
        print(f"  ✗ Error reordering columns: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_dataset_columns(syn, dataset_id, verbose=True):
    """
    Retrieve and display dataset columns for verification.

    Shows column names, types, facet types, and size constraints.

    Args:
        syn: Synapse client
        dataset_id: Dataset Synapse ID
        verbose: If True, show detailed column information

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        dataset = Dataset(id=dataset_id).get(include_columns=True)

        # Use dataset.columns (consistent with reorder function)
        if not hasattr(dataset, 'columns') or not dataset.columns:
            print(f"  ℹ️  Dataset has no columns")
            return True

        # dataset.columns is a dict, get the Column objects
        columns = list(dataset.columns.values())
        print(f"  📊 Total columns: {len(columns)}")

        # Group by facet type
        faceted = [c for c in columns if c.facet_type]
        non_faceted = [c for c in columns if not c.facet_type]

        print(f"  🔍 Faceted (searchable): {len(faceted)}")
        print(f"  📝 Non-faceted: {len(non_faceted)}")

        if verbose and faceted:
            print("\n  Faceted columns:")
            for col in faceted:
                size_info = ''
                if col.maximum_size:
                    size_info = f" (max: {col.maximum_size})"
                elif col.maximum_list_length:
                    size_info = f" (max list: {col.maximum_list_length})"
                facet_display = col.facet_type.value if col.facet_type else 'None'
                print(f"   • {col.name}: {col.column_type.value}{size_info} [{facet_display}]")

            if len(faceted) > 10:
                print(f"   ... and {len(faceted) - 10} more faceted columns")

        return True

    except Exception as e:
        print(f"  ✗ Error verifying columns: {e}")
        import traceback
        traceback.print_exc()
        return False


def add_staging_folder_to_dataset(syn, dataset_id, staging_folder_id, dry_run=True):
    """
    Recursively add entire staging folder contents to dataset.

    This is a cleaner alternative to adding files one-by-one.

    Args:
        syn: Synapse client
        dataset_id: Dataset Synapse ID
        staging_folder_id: Staging folder Synapse ID
        dry_run: If True, only print what would be done

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if dry_run:
            print(f"  [DRY_RUN] Would add staging folder {staging_folder_id} to dataset")
            return True

        dataset = Dataset(id=dataset_id).get()
        dataset.add_item(Folder(id=staging_folder_id))
        dataset.store()
        print(f"  ✓ Added staging folder to dataset")
        return True

    except Exception as e:
        print(f"  ✗ Error adding staging folder to dataset: {e}")
        import traceback
        traceback.print_exc()
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


def upload_file_new_versions(syn, file_annotations, local_files_dir,
                              version_label=None, version_comment=None,
                              dry_run=True, verbose=False):
    """
    Upload local files as new versions of existing Synapse file entities.

    For each entry in file_annotations, find a matching file in local_files_dir
    by filename, then upload it to the same syn_id (creating a new version).
    Annotations are applied during upload.

    Args:
        syn: Synapse client
        file_annotations: {syn_id: {filename: annotations_dict}}
        local_files_dir: Local directory containing prepared file versions
        version_label: Version label (e.g., "v4-JAN")
        version_comment: Version comment
        dry_run: If True, only show what would be done
        verbose: Show detailed output

    Returns:
        Tuple of (success_count, error_count, skipped_count)
    """
    success_count = 0
    error_count = 0
    skipped_count = 0

    local_files = {}
    if os.path.isdir(local_files_dir):
        for fname in os.listdir(local_files_dir):
            local_files[fname.lower()] = os.path.join(local_files_dir, fname)

    for syn_id, file_data in file_annotations.items():
        filename = list(file_data.keys())[0]
        annotations = list(file_data.values())[0]

        # Try to find matching local file (case-insensitive)
        local_path = local_files.get(filename.lower())
        if local_path is None:
            if verbose:
                print(f"  [SKIP] No local file found matching '{filename}' ({syn_id})")
            skipped_count += 1
            continue

        try:
            cleaned = clean_annotations_for_synapse(annotations)

            if dry_run:
                label_str = f" with version label '{version_label}'" if version_label else ""
                print(f"  [DRY_RUN] Would upload {os.path.basename(local_path)} -> {syn_id}{label_str}")
                success_count += 1
            else:
                file_entity = File(
                    path=local_path,
                    id=syn_id,
                    name=filename,
                    version_label=version_label,
                    version_comment=version_comment,
                    annotations=cleaned,
                )
                file_entity.store()
                if verbose:
                    print(f"  ✓ Uploaded new version of {filename} ({syn_id})")
                success_count += 1

        except Exception as e:
            err_str = str(e)
            if 'UNIQUE_REVISION_LABEL' in err_str or 'Duplicate entry' in err_str:
                print(f"  [SKIP] Version '{version_label}' already exists for {filename} ({syn_id}) — skipping")
                skipped_count += 1
            else:
                print(f"  ✗ Error uploading new version of {filename} ({syn_id}): {e}")
                error_count += 1

    return success_count, error_count, skipped_count


def upload_new_versions_from_staging(syn, file_annotations: dict,
                                      version_label=None, version_comment=None,
                                      dry_run=True, verbose=False) -> tuple[int, int, int]:
    """
    For each file in file_annotations that has _staging_id, download the staging
    file and upload it as a new version of the existing entity (the outer syn_id key).

    Returns: (success_count, error_count, skipped_count)
    """
    import tempfile
    success_count = error_count = skipped_count = 0
    download_dir = tempfile.mkdtemp(prefix='sdm_upload_')

    for syn_id, file_data in file_annotations.items():
        filename = list(file_data.keys())[0]
        annotations = list(file_data.values())[0]
        staging_id = annotations.get('_staging_id')

        if not staging_id:
            skipped_count += 1
            continue

        local_path = download_file_for_analysis(syn, staging_id, download_dir)
        if not local_path:
            print(f"  ✗ Could not download staging file {staging_id} for {filename}")
            error_count += 1
            continue

        try:
            cleaned = clean_annotations_for_synapse(annotations)
            if dry_run:
                label_str = f" with label '{version_label}'" if version_label else ""
                print(f"  [DRY_RUN] Would upload {staging_id} → {syn_id} ({filename}){label_str}")
                success_count += 1
            else:
                file_entity = File(
                    path=local_path,
                    id=syn_id,
                    name=filename,
                    version_label=version_label,
                    version_comment=version_comment,
                    annotations=cleaned,
                )
                file_entity.store()
                if verbose:
                    print(f"  ✓ Uploaded new version: {filename} ({syn_id})")
                success_count += 1
        except Exception as e:
            err_str = str(e)
            if 'UNIQUE_REVISION_LABEL' in err_str or 'Duplicate entry' in err_str:
                print(f"  [SKIP] Version '{version_label}' already exists for {filename} ({syn_id}) — skipping")
                skipped_count += 1
            else:
                print(f"  ✗ Error uploading {filename} ({syn_id}): {e}")
                error_count += 1

    return success_count, error_count, skipped_count


def move_and_add_new_files(syn, new_file_ids_annotations, release_folder_id,
                            dataset_id, dry_run=True, verbose=False,
                            version_label=None, version_comment=None):
    """
    Move new-only staging files to release folder, add to dataset, apply annotations.

    Used when staging has files that don't exist in the release dataset yet.

    Args:
        syn: Synapse client
        new_file_ids_annotations: {syn_id: {filename: annotations_dict}}
                                   (files from staging not yet in release)
        release_folder_id: Synapse ID of release folder
        dataset_id: Synapse ID of dataset to add files to
        dry_run: If True, only show what would be done
        verbose: Show detailed output
        version_label: Optional version label to apply (creates a new version)
        version_comment: Optional version comment

    Returns:
        Tuple of (success_count, error_count)
    """
    success_count = 0
    error_count = 0

    for syn_id, file_data in new_file_ids_annotations.items():
        filename = list(file_data.keys())[0]
        annotations = list(file_data.values())[0]

        try:
            cleaned = clean_annotations_for_synapse(annotations)

            if dry_run:
                print(f"  [DRY_RUN] Would move {filename} ({syn_id}) -> {release_folder_id}")
                print(f"  [DRY_RUN] Would add {syn_id} to dataset {dataset_id}")
                print(f"  [DRY_RUN] Would apply {len(cleaned)} annotations to {syn_id}")
                success_count += 1
                continue

            # 1. Move to release folder (rename staging entity to form name if needed)
            file_entity = syn.get(syn_id, downloadFile=False)
            if file_entity.name != filename:
                file_entity.name = filename
            file_entity.parentId = release_folder_id
            syn.store(file_entity, forceVersion=False)
            if verbose:
                print(f"  ✓ Moved {filename} ({syn_id}) to {release_folder_id}")

            # 2. Add to dataset
            dataset = Dataset(id=dataset_id).get()
            dataset.add_item(File(id=syn_id))
            dataset.store()
            if verbose:
                print(f"  ✓ Added {syn_id} to dataset {dataset_id}")

            # 3. Apply annotations (and version label if provided)
            entity = syn.get(syn_id, downloadFile=False)
            entity.annotations = cleaned
            if version_comment:
                entity['versionComment'] = version_comment
            syn.store(entity, forceVersion=bool(version_label),
                      versionLabel=version_label or None)
            if verbose:
                label_str = f" with label '{version_label}'" if version_label else ""
                print(f"  ✓ Applied {len(cleaned)} annotations to {filename}{label_str}")

            success_count += 1

        except Exception as e:
            print(f"  ✗ Error processing new file {filename} ({syn_id}): {e}")
            error_count += 1

    return success_count, error_count


def verify_update_results(syn, dataset_id, expected_syn_ids,
                           expected_version_label=None,
                           release_folder_id=None,
                           verbose=True):
    """
    Verify update results: version labels, parent folders, dataset membership.

    Args:
        syn: Synapse client
        dataset_id: Synapse ID of the dataset
        expected_syn_ids: List of syn IDs to verify
        expected_version_label: Expected version label on file entities (optional)
        release_folder_id: Expected parent folder ID (optional)
        verbose: Print per-file results

    Returns:
        dict with keys: verified_versions, verified_folders, verified_membership, failures
    """
    results = {
        'verified_versions': 0,
        'verified_folders': 0,
        'verified_membership': 0,
        'failures': []
    }

    try:
        dataset = Dataset(id=dataset_id).get()
        dataset_item_ids = {item.id for item in dataset.items}
    except Exception as e:
        print(f"  ✗ Could not retrieve dataset items for {dataset_id}: {e}")
        dataset_item_ids = set()

    for syn_id in expected_syn_ids:
        file_failures = []
        try:
            entity = syn.get(syn_id, downloadFile=False)

            # Check version label
            if expected_version_label:
                actual_label = getattr(entity, 'versionLabel', None)
                if actual_label == expected_version_label:
                    results['verified_versions'] += 1
                else:
                    file_failures.append(
                        f"version label: expected '{expected_version_label}', got '{actual_label}'"
                    )

            # Check parent folder
            if release_folder_id:
                actual_parent = getattr(entity, 'parentId', None)
                if actual_parent == release_folder_id:
                    results['verified_folders'] += 1
                else:
                    file_failures.append(
                        f"parent folder: expected '{release_folder_id}', got '{actual_parent}'"
                    )

            # Check dataset membership
            if syn_id in dataset_item_ids:
                results['verified_membership'] += 1
            else:
                file_failures.append(f"not found in dataset {dataset_id}")

            if verbose:
                status = "✓" if not file_failures else "✗"
                print(f"  {status} {entity.name} ({syn_id})")
                for failure in file_failures:
                    print(f"      ✗ {failure}")

        except Exception as e:
            file_failures.append(f"could not retrieve entity: {e}")
            if verbose:
                print(f"  ✗ {syn_id}: {e}")

        if file_failures:
            results['failures'].append({'syn_id': syn_id, 'issues': file_failures})

    total = len(expected_syn_ids)
    print(f"\n  Verification summary ({total} files):")
    if expected_version_label:
        print(f"    Version labels correct : {results['verified_versions']}/{total}")
    if release_folder_id:
        print(f"    Folders correct        : {results['verified_folders']}/{total}")
    print(f"    Dataset membership     : {results['verified_membership']}/{total}")
    print(f"    Failures               : {len(results['failures'])}")

    return results


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


def delete_file_versions_by_label(syn, syn_id, version_labels, dry_run=True, verbose=False):
    """
    Delete all versions of a Synapse file entity whose versionLabel matches any of the given labels.

    Args:
        syn: Synapse client
        syn_id: Synapse entity ID
        version_labels: List of version label strings to delete (e.g. ["v5-FEB_test", "v5-FEB_test_v2"])
        dry_run: If True, only show what would be deleted
        verbose: Show detailed output

    Returns:
        (deleted_count, skipped_count, error_count)
    """
    label_set = set(version_labels)
    deleted = skipped = errors = 0

    try:
        # Paginate through all versions
        versions = []
        offset = 0
        limit = 100
        while True:
            page = syn.restGET(f"/entity/{syn_id}/version?offset={offset}&limit={limit}")
            batch = page.get('results', [])
            versions.extend(batch)
            if len(batch) < limit:
                break
            offset += limit

        matches = [(v['versionNumber'], v.get('versionLabel', '')) for v in versions
                   if v.get('versionLabel') in label_set]

        if not matches:
            if verbose:
                print(f"  [SKIP] No matching versions found on {syn_id}")
            skipped += 1
            return deleted, skipped, errors

        for version_number, label in matches:
            if dry_run:
                print(f"  [DRY_RUN] Would delete {syn_id} version {version_number} (label='{label}')")
                deleted += 1
            else:
                try:
                    syn.delete(syn_id, version=version_number)
                    if verbose:
                        print(f"  ✓ Deleted {syn_id} version {version_number} (label='{label}')")
                    deleted += 1
                except Exception as e:
                    print(f"  ✗ Error deleting {syn_id} v{version_number}: {e}")
                    errors += 1

    except Exception as e:
        print(f"  ✗ Error listing versions for {syn_id}: {e}")
        errors += 1

    return deleted, skipped, errors


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
                               file_type='ClinicalFile', all_schemas=None,
                               dataset_type=None, dry_run=True):
    """
    Create an entity view for dataset files with type-aware columns and size constraints.

    Args:
        syn: Synapse client
        dataset_id: Dataset Synapse ID (or staging folder ID)
        dataset_name: Dataset name
        project_id: Project ID to create view in
        file_type: Type of files (kept for backward compatibility)
        all_schemas: Schema dictionary (kept for backward compatibility)
        dataset_type: Dataset type ('ClinicalDataset', 'OmicDataset', etc.)
                     If not provided, will derive from file_type
        dry_run: If True, only show what would be created

    Returns:
        Entity view ID if created, None otherwise
    """
    view_name = f"{dataset_name}_EntityView"

    # Auto-detect dataset type if not provided
    if not dataset_type and file_type:
        # Convert file_type to dataset_type (e.g., 'ClinicalFile' -> 'ClinicalDataset')
        dataset_type = file_type.replace('File', 'Dataset')
        if dataset_type == 'Dataset':
            dataset_type = 'ClinicalDataset'  # Default

    # Get column schema for this dataset type
    columns_to_add = get_entity_view_column_schema(dataset_type)

    # Build columns with size constraints
    all_columns = []

    for col_info in columns_to_add:
        try:
            # Build column kwargs
            col_kwargs = {
                'name': col_info['name'],
                'column_type': col_info['type'],
                'facet_type': col_info.get('facet')
            }

            # Add size constraints to prevent 64KB row limit violations
            if col_info['type'] == ColumnType.STRING and 'max_size' in col_info:
                col_kwargs['maximum_size'] = col_info['max_size']
            elif col_info['type'] == ColumnType.STRING_LIST and 'max_list_len' in col_info:
                col_kwargs['maximum_list_length'] = col_info['max_list_len']

            col = Column(**col_kwargs)
            all_columns.append(col)
        except Exception as e:
            print(f"    ⚠️  Could not add column {col_info['name']}: {e}")

    if dry_run:
        print(f"  [DRY_RUN] Would create entity view '{view_name}' ({dataset_type})")
        print(f"    Scope: {dataset_id}")
        print(f"    Columns: {len(all_columns)} columns")
        print(f"    Columns: {', '.join([c.name for c in all_columns[:10]])}{'...' if len(all_columns) > 10 else ''}")
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
            # Store the entity view
            created_view = entity_view.store()
            print(f"  ✓ Entity view created: {created_view.id} ({dataset_type})")
            print(f"  ✓ Total columns: {len(all_columns)} with size constraints")
            print(f"  🔗 URL: https://www.synapse.org/#!Synapse:{created_view.id}")
            return created_view.id
        except Exception as e:
            print(f"  ✗ Error creating entity view: {e}")
            import traceback
            traceback.print_exc()
            return None


def reorder_entity_view_columns(syn, view_id, dataset_type=None, dry_run=True):
    """
    Reorder entity view columns based on priority template.

    Puts important columns first for better UX in Synapse UI.

    Args:
        syn: Synapse client
        view_id: Entity view Synapse ID
        dataset_type: Dataset type ('ClinicalDataset', 'OmicDataset', etc.)
                     If not provided, defaults to 'ClinicalDataset'
        dry_run: If True, only print what would be done

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Use default if not provided
        if not dataset_type:
            dataset_type = 'ClinicalDataset'

        # Get entity view with columns using the models API (same as datasets)
        # This ensures columns are properly loaded
        from synapseclient.models import Table
        entity_view = Table(id=view_id).get(include_columns=True)

        # Get current column order (using entity_view.columns like datasets)
        if not hasattr(entity_view, 'columns') or not entity_view.columns:
            print(f"  ℹ️  No columns to reorder")
            return True

        current_columns = list(entity_view.columns.keys())

        # Build ordered list from template (using entity view specific template)
        template_order = get_entity_view_column_order_template(dataset_type)

        # Filter template to only include columns that exist in view
        final_order = []
        for col in template_order:
            if col in current_columns:
                final_order.append(col)

        # Append any remaining columns not in template (to handle custom columns)
        remaining_cols = [col for col in current_columns if col not in final_order]
        final_order.extend(remaining_cols)

        if dry_run:
            print(f"  [DRY_RUN] Would reorder {len(final_order)} columns in entity view")
            print(f"  [DRY_RUN] Current order: {', '.join(current_columns[:10])}{'...' if len(current_columns) > 10 else ''}")
            print(f"  [DRY_RUN] New order: {', '.join(final_order[:10])}{'...' if len(final_order) > 10 else ''}")
            return True

        # Apply reordering (same pattern as datasets)
        for target_index, col_name in enumerate(final_order):
            entity_view.reorder_column(name=col_name, index=target_index)

        # Store changes
        entity_view.store()
        print(f"  ✓ Reordered {len(final_order)} columns in entity view ({dataset_type})")

        return True

    except Exception as e:
        print(f"  ✗ Error reordering entity view columns: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_entity_view_columns(syn, view_id, verbose=True):
    """
    Retrieve and display entity view columns for verification.

    Shows column names, types, facet types, and size constraints.

    Args:
        syn: Synapse client
        view_id: Entity view Synapse ID
        verbose: If True, show detailed column information

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Use models API to get entity view with columns (same as datasets)
        from synapseclient.models import Table
        entity_view = Table(id=view_id).get(include_columns=True)

        # Use entity_view.columns (consistent with datasets)
        if not hasattr(entity_view, 'columns') or not entity_view.columns:
            print(f"  ℹ️  Entity view has no columns")
            return True

        # entity_view.columns is a dict, get the Column objects
        columns = list(entity_view.columns.values())
        print(f"  📊 Total columns: {len(columns)}")

        # Group by facet type
        faceted = [c for c in columns if c.facet_type]
        non_faceted = [c for c in columns if not c.facet_type]

        print(f"  🔍 Faceted (searchable): {len(faceted)}")
        print(f"  📝 Non-faceted: {len(non_faceted)}")

        if verbose and faceted:
            print("\n  Faceted columns:")
            for col in faceted:
                size_info = ''
                if col.maximum_size:
                    size_info = f" (max: {col.maximum_size})"
                elif col.maximum_list_length:
                    size_info = f" (max list: {col.maximum_list_length})"
                facet_display = col.facet_type.value if col.facet_type else 'None'
                print(f"   • {col.name}: {col.column_type.value}{size_info} [{facet_display}]")

            if len(faceted) > 10:
                print(f"   ... and {len(faceted) - 10} more faceted columns")

        return True

    except Exception as e:
        print(f"  ✗ Error verifying entity view columns: {e}")
        import traceback
        traceback.print_exc()
        return False


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

def create_link_file_entity(syn, name, url, parent_id, annotations=None, dry_run=True):
    """
    Create a File entity with external URL reference (no file upload).

    Args:
        syn: Synapse client
        name: Name for the link file entity
        url: External URL to reference
        parent_id: Parent project or folder ID
        annotations: Optional annotations dict
        dry_run: If True, only show what would be created

    Returns:
        File entity ID if created, None otherwise
    """
    try:
        if dry_run:
            print(f"  [DRY_RUN] Would create link file '{name}'")
            print(f"    URL: {url}")
            print(f"    Parent: {parent_id}")
            if annotations:
                print(f"    Annotations: {len(annotations)} fields")
            return "syn_DRYRUN_LINK"

        # Create a temporary placeholder file (required even though not uploaded)
        temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt')
        temp_file.write(f"External link: {url}")
        temp_file.close()

        try:
            # Create File entity with external URL (synapse_store=False prevents upload)
            link_file = File(
                parent_id=parent_id,
                name=name,
                path=temp_file.name,
                external_url=url,
                synapse_store=False
            )

            # Add annotations if provided
            if annotations:
                cleaned = clean_annotations_for_synapse(annotations)
                link_file.annotations = cleaned

            # Store the file entity
            stored_file = link_file.store()

            print(f"  ✓ Created link file: {stored_file.id}")
            print(f"    Name: {name}")
            print(f"    External URL: {url}")
            return stored_file.id

        finally:
            # Clean up temporary file
            os.unlink(temp_file.name)

    except Exception as e:
        print(f"  ✗ Error creating link file: {e}")
        import traceback
        traceback.print_exc()
        return None


def add_link_to_dataset(syn, link_id, dataset_id, dry_run=True):
    """
    Add a File entity (link) to a dataset.

    Args:
        syn: Synapse client
        link_id: File entity Synapse ID
        dataset_id: Dataset Synapse ID
        dry_run: If True, only show what would be done

    Returns:
        True if successful, False otherwise
    """
    try:
        if dry_run:
            print(f"  [DRY_RUN] Would add link file {link_id} to dataset {dataset_id}")
            return True

        dataset = Dataset(dataset_id).get()
        file_ref = File(id=link_id)
        dataset.add_item(file_ref)
        dataset.store()

        print(f"  ✓ Added link file {link_id} to dataset {dataset_id}")
        return True

    except Exception as e:
        print(f"  ✗ Error adding link file to dataset: {e}")
        import traceback
        traceback.print_exc()
        return False


def handle_add_link_file(args, config):
    """Handle ADD-LINK-FILE command - create link file and optionally add to dataset"""
    print("\n" + "=" * 60)
    print("CREATE LINK FILE ENTITY")
    print("=" * 60)

    # Validate URL
    if not args.url or not args.url.strip():
        print("❌ Error: --url is required and cannot be empty")
        sys.exit(1)

    # Parse annotations if provided
    annotations = {}
    if args.annotations:
        try:
            annotations = json.loads(args.annotations)
        except json.JSONDecodeError as e:
            print(f"❌ Error: Invalid JSON for --annotations: {e}")
            sys.exit(1)

    # Determine parent ID (priority: parent-id > dataset-id > project)
    if args.parent_id:
        parent_id = args.parent_id
        print(f"Using parent ID from --parent-id: {parent_id}")
    elif args.dataset_id:
        parent_id = args.dataset_id
        print(f"Using parent ID from --dataset-id: {parent_id}")
    else:
        parent_id = config.SYNAPSE_PROJECT_ID
        print(f"Using parent ID from config (project): {parent_id}")

    # Connect to Synapse
    print("\nConnecting to Synapse...")
    syn = connect_to_synapse(config)

    # Create link file
    print("\n" + "=" * 60)
    print("CREATING LINK FILE")
    print("=" * 60)

    link_id = create_link_file_entity(
        syn, args.name, args.url, parent_id,
        annotations, config.DRY_RUN
    )

    if not link_id:
        print("❌ Failed to create link file")
        sys.exit(1)

    # Add to dataset if specified
    if args.dataset_id:
        print("\n" + "=" * 60)
        print("ADDING LINK TO DATASET")
        print("=" * 60)

        success = add_link_to_dataset(syn, link_id, args.dataset_id, config.DRY_RUN)

        if not success:
            print("⚠️  Warning: Link created but failed to add to dataset")

    # Summary
    print("\n" + "=" * 60)
    print("✅ LINK FILE CREATION COMPLETE")
    print("=" * 60)
    print(f"Link ID: {link_id}")
    print(f"Name: {args.name}")
    print(f"URL: {args.url}")
    if args.dataset_id:
        print(f"Dataset: {args.dataset_id}")
    print(f"DRY_RUN: {config.DRY_RUN}")

    if config.DRY_RUN:
        print("\n⚠️  This was a DRY_RUN - no changes made")
        print("Run with --execute to apply changes")


def handle_generate_template(args, config):
    """Handle GENERATE-TEMPLATE command - create empty dataset annotation template"""
    print("\n" + "=" * 60)
    print("GENERATING DATASET ANNOTATION TEMPLATE")
    print("=" * 60)

    # Load schemas
    print("\nLoading schemas...")
    all_schemas = get_all_schemas(config.SCHEMA_BASE_PATH, config.VERBOSE)

    # Determine dataset type
    dataset_type_map = {
        'Clinical': 'ClinicalDataset',
        'Omic': 'OmicDataset',
        'Dataset': 'Dataset'
    }

    dataset_type = dataset_type_map.get(args.type, 'Dataset')
    print(f"Dataset type: {dataset_type}")

    # Generate template
    template = create_annotation_template(all_schemas, dataset_type)

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        # Default to annotations directory
        output_filename = f"{args.type.lower()}_dataset_template.json"
        output_path = os.path.join(config.ANNOTATIONS_DIR, output_filename)

    # Ensure parent directory exists
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)

    # Save template
    with open(output_path, 'w') as f:
        json.dump(template, f, indent=2)

    print("\n" + "=" * 60)
    print("✅ TEMPLATE GENERATED SUCCESSFULLY")
    print("=" * 60)
    print(f"Output file: {output_path}")
    print(f"Dataset type: {dataset_type}")
    print(f"Fields: {len([k for k in template.keys() if not k.startswith('_')])}")
    print("\n💡 Edit this file to add your dataset metadata")
    if args.type == 'Dataset':
        print("   Note: You can also use 'Clinical' or 'Omic' for more specific schemas")


def handle_generate_file_templates(args, config):
    """Generate per-file annotation templates from a Synapse folder."""
    print("\n" + "=" * 60)
    print("GENERATE FILE TEMPLATES")
    print("=" * 60)

    # Load schemas
    print("\nLoading schemas...")
    all_schemas = get_all_schemas(config.SCHEMA_BASE_PATH, config.VERBOSE)

    # Connect to Synapse
    print("\nConnecting to Synapse...")
    syn = connect_to_synapse(config)

    # Step 1: Enumerate files
    print("\n" + "=" * 60)
    print("STEP 1: ENUMERATING FILES")
    print("=" * 60)
    cache_path = os.path.join(
        getattr(config, 'BASE_DIR', tempfile.gettempdir()),
        f".walkthrough_cache_{args.folder}.json"
    )
    if not getattr(args, 'refresh_walkthrough', False) and os.path.exists(cache_path):
        if config.VERBOSE:
            print(f"  Loading file walkthrough from cache: {cache_path}")
        with open(cache_path, 'r') as f:
            files_dict = json.load(f)
    else:
        files_dict = enumerate_files_with_folders(
            syn, args.folder, recursive=True, verbose=config.VERBOSE
        )
        with open(cache_path, 'w') as f:
            json.dump(files_dict, f, indent=2)
        if config.VERBOSE:
            print(f"  Walkthrough cached to: {cache_path}")

    if not files_dict:
        print("❌ No files found in folder")
        sys.exit(1)

    # Step 2: Generate annotation templates
    print("\n" + "=" * 60)
    print("STEP 2: GENERATING ANNOTATION TEMPLATES")
    print("=" * 60)

    # Expand any directory paths in --metadata to constituent CSV/XLSX files
    if getattr(args, 'metadata', None):
        expanded = []
        for p in args.metadata:
            if os.path.isdir(p):
                dir_files = sorted(
                    str(f) for f in Path(p).iterdir()
                    if f.suffix.lower() in ('.csv', '.xlsx', '.xls')
                )
                if not dir_files:
                    print(f"  Warning: No CSV/XLSX files found in directory {p}")
                expanded.extend(dir_files)
            else:
                expanded.append(p)
        args.metadata = expanded

    # Step 1: Load mapping + metadata (before per-file loop)
    mapping = load_mapping_dict(args.mapping) if getattr(args, 'mapping', None) else None
    metadata_index = {}
    if getattr(args, 'metadata', None) and mapping:
        def _targets_include(v, field):
            t = v['target'] if isinstance(v, dict) else v
            return field in (t if isinstance(t, list) else [t])

        join_col = next(
            (k for k, v in mapping.items() if _targets_include(v, 'originalSubjectId')),
            'subject_id'
        )
        metadata_index = load_all_metadata_files(args.metadata, join_col)
        print(f"  Loaded {len(metadata_index)} subjects from {len(args.metadata)} metadata file(s)")

    dataset_config = {'dataset_type': args.type} if args.type else {}
    annotations_output = {}
    metadata_fill_count = 0
    for syn_id, file_info in files_dict.items():
        filename = file_info['name']
        existing_annotations = file_info['annotations']

        file_type = detect_file_type(filename, all_schemas=all_schemas, dataset_config=dataset_config)
        template = create_annotation_template(all_schemas, file_type)
        merged = merge_annotations_smartly(existing_annotations, template)

        # Step 2: Fill from metadata if available
        if metadata_index and mapping:
            subject_id = file_info['path'].split('/')[-1] if file_info.get('path') else None
            if subject_id and subject_id in metadata_index:
                # Enrich metadata with file-derived fields
                folder_path = file_info.get('path', '')
                metadata_row = enrich_metadata_with_file_info(metadata_index[subject_id], filename, folder_path)
                merged = fill_template_from_metadata(merged, metadata_row, mapping)
                metadata_fill_count += 1
            elif subject_id:
                print(f"  Warning: No metadata match for subject_id '{subject_id}' ({filename})")
                # Still enrich with file info even if no metadata match
                if mapping:
                    folder_path = file_info.get('path', '')
                    metadata_row = enrich_metadata_with_file_info({}, filename, folder_path)
                    merged = fill_template_from_metadata(merged, metadata_row, mapping)
        elif mapping:
            # No metadata file provided, but we have mapping - still enrich from filename
            folder_path = file_info.get('path', '')
            metadata_row = enrich_metadata_with_file_info({}, filename, folder_path)
            merged = fill_template_from_metadata(merged, metadata_row, mapping)

        annotations_output[syn_id] = {filename: merged}

    # Step 3: Summary counter
    if metadata_index:
        print(f"  Metadata-filled: {metadata_fill_count} / {len(files_dict)} files matched a metadata row")

    # Optional AI enhancement
    if config.AI_ENABLED and not (hasattr(args, 'skip_ai') and args.skip_ai):
        name = args.name or args.folder
        download_dir = os.path.join(config.BASE_DIR, "downloads", name.replace(" ", "_"))
        annotations_output = enhance_annotations_with_ai(
            syn, files_dict, annotations_output, all_schemas,
            download_dir, config
        )

    # Determine output path
    name = args.name or args.folder
    if args.output:
        output_path = args.output
    else:
        output_path = os.path.join(config.ANNOTATIONS_DIR, f"{name}_file_templates.json")

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    save_annotation_file(annotations_output, output_path)

    print("\n" + "=" * 60)
    print("✅ FILE TEMPLATES GENERATED SUCCESSFULLY")
    print("=" * 60)
    print(f"Output file: {output_path}")
    print(f"Total files: {len(annotations_output)}")
    print("\n💡 Edit this file to fill in annotation values")


def handle_apply_file_annotations(args, config):
    """Apply edited per-file annotation JSON to Synapse file entities."""
    print("\n" + "=" * 60)
    print("APPLY FILE ANNOTATIONS")
    print("=" * 60)

    print("\nLoading schemas...")
    all_schemas = get_all_schemas(config.SCHEMA_BASE_PATH, config.VERBOSE)

    if not os.path.exists(args.annotations_file):
        print(f"❌ Error: Annotations file not found: {args.annotations_file}")
        sys.exit(1)

    with open(args.annotations_file) as f:
        file_annotations = json.load(f)
    print(f"✓ Loaded annotations from {args.annotations_file} ({len(file_annotations)} file entries)")

    print("\nConnecting to Synapse...")
    syn = connect_to_synapse(config)

    if not args.skip_validation:
        print("\n" + "=" * 60)
        print("VALIDATING ANNOTATIONS")
        print("=" * 60)
        validation_errors = False
        for syn_id, file_data in file_annotations.items():
            filename = list(file_data.keys())[0]
            annots = file_data[filename]
            file_type = annots.get('_file_type', 'File')
            is_valid, errors, warnings = validate_annotation_against_schema(annots, file_type, all_schemas)
            for w in warnings:
                print(f"  ⚠ {filename}: {w}")
            if errors:
                for e in errors:
                    print(f"  ✗ {filename}: {e}")
                validation_errors = True
        if validation_errors:
            print("\n❌ Validation errors found. Fix them or re-run with --skip-validation.")
            sys.exit(1)
        else:
            print("✓ All annotations valid")

    print("\n" + "=" * 60)
    print("APPLYING FILE ANNOTATIONS")
    print("=" * 60)

    success_count, error_count = apply_annotations_to_files(
        syn, file_annotations, dry_run=config.DRY_RUN, verbose=config.VERBOSE
    )

    print("\n" + "=" * 60)
    print(f"  Files succeeded : {success_count}")
    print(f"  Files failed    : {error_count}")
    if config.DRY_RUN:
        print("\n✅ DRY RUN COMPLETE — re-run with --execute to apply changes")
    elif error_count == 0:
        print("\n✅ FILE ANNOTATIONS APPLIED SUCCESSFULLY")
    else:
        print("\n⚠ FILE ANNOTATIONS APPLIED WITH ERRORS")
    print("=" * 60)


def handle_create_workflow(args, config):
    """Handle CREATE workflow - create new dataset from scratch"""
    print("\n" + "=" * 60)
    print("WORKFLOW: CREATE NEW DATASET")
    print("=" * 60)

    # Detect link dataset mode (CLI flag or config)
    is_link_dataset = args.link_dataset if hasattr(args, 'link_dataset') else False
    dataset_config = config.get_dataset_config(args.use_config) if hasattr(args, 'use_config') and args.use_config else {}
    if not is_link_dataset and dataset_config:
        is_link_dataset = dataset_config.get('link_dataset', False)

    if is_link_dataset:
        print("🔗 LINK DATASET MODE: Creating dataset without files")

    if not is_link_dataset and not args.staging_folder:
        print("❌ Error: --staging-folder required for CREATE workflow")
        sys.exit(1)

    if not args.dataset_name:
        print("❌ Error: --dataset-name required for CREATE workflow")
        sys.exit(1)

    # Load schemas
    print("\nLoading schemas...")
    all_schemas = get_all_schemas(config.SCHEMA_BASE_PATH, config.VERBOSE)

    # Get dataset-specific configuration (for type detection)
    if not dataset_config:
        dataset_config = config.get_dataset_config(args.dataset_name)
    if dataset_config.get('dataset_type'):
        print(f"Using configured dataset type: {dataset_config['dataset_type']}")

    # Connect to Synapse
    print("\nConnecting to Synapse...")
    syn = connect_to_synapse(config)

    # Step 1: Enumerate files (SKIP FOR LINK DATASETS)
    if not is_link_dataset:
        print("\n" + "=" * 60)
        print("STEP 1: ENUMERATING FILES")
        print("=" * 60)
        files_dict = enumerate_files_with_folders(
            syn, args.staging_folder, recursive=True, verbose=config.VERBOSE
        )

        if not files_dict:
            print("❌ No files found in staging folder")
            sys.exit(1)
    else:
        print("\n" + "=" * 60)
        print("STEP 1: SKIPPING FILE ENUMERATION (Link Dataset)")
        print("=" * 60)
        print("🔗 Link datasets reference external URLs only")
        files_dict = {}

    # Step 2: Generate annotation templates (SKIP FILE ANNOTATIONS FOR LINK DATASETS)
    if not is_link_dataset:
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
    else:
        print("\n" + "=" * 60)
        print("STEP 2: SKIPPING FILE ANNOTATIONS (Link Dataset)")
        print("=" * 60)
        print("🔗 No files to annotate")
        annotations_output = {}

    # Generate dataset annotation template (checks config first, then pattern matching, then defaults to Dataset)
    print("\n" + "=" * 60)
    print("GENERATING DATASET ANNOTATIONS")
    print("=" * 60)
    dataset_type = detect_dataset_type(args.dataset_name, args.staging_folder if not is_link_dataset else None, dataset_config=dataset_config)

    # Use AI to generate dataset annotations if enabled
    if config.AI_ENABLED and not is_link_dataset:
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
    if not is_link_dataset:
        print(f"File annotations: {output_file}")
    print(f"Dataset annotations: {dataset_output_file}")
    print(f"Total files: {len(annotations_output)}")
    print("\n⚠️  MANUAL STEP: Edit the annotation files")
    if is_link_dataset:
        print("   🔗 IMPORTANT: Add a 'url' field pointing to the external dataset location")
    print(f"\nAfter editing, continue with:")
    if is_link_dataset:
        print(f"  python {sys.argv[0]} create --from-annotations --link-dataset \\")
    else:
        print(f"  python {sys.argv[0]} create --from-annotations \\")
        print(f"    --staging-folder {args.staging_folder} \\")
    print(f"    --dataset-name {args.dataset_name}")


def handle_create_from_annotations(args, config):
    """Handle CREATE workflow from pre-edited annotations"""
    print("\n" + "=" * 60)
    print("WORKFLOW: CREATE DATASET FROM ANNOTATIONS")
    print("=" * 60)

    # Detect link dataset mode
    is_link_dataset = args.link_dataset if hasattr(args, 'link_dataset') else False
    dataset_config = config.get_dataset_config(args.use_config) if hasattr(args, 'use_config') and args.use_config else {}
    if not is_link_dataset and dataset_config:
        is_link_dataset = dataset_config.get('link_dataset', False)

    if is_link_dataset:
        print("🔗 LINK DATASET MODE: Creating dataset without files")

    # Load annotations
    dataset_annotations_file = os.path.join(config.ANNOTATIONS_DIR, f"{args.dataset_name}_dataset_annotations.json")
    dataset_annotations = load_annotation_file(dataset_annotations_file)

    # Load file annotations only if not link dataset
    if not is_link_dataset:
        file_annotations_file = os.path.join(config.ANNOTATIONS_DIR, f"{args.dataset_name}_annotations.json")
        file_annotations = load_annotation_file(file_annotations_file)

        if not file_annotations:
            print(f"❌ No file annotations found at {file_annotations_file}")
            sys.exit(1)
    else:
        file_annotations = {}
        print("🔗 Skipping file annotations (link dataset mode)")

    # Load schemas
    all_schemas = get_all_schemas(config.SCHEMA_BASE_PATH, config.VERBOSE)

    # Connect to Synapse
    syn = connect_to_synapse(config)

    # Validate annotations
    print("\n" + "=" * 60)
    print("STEP 1: VALIDATING ANNOTATIONS")
    print("=" * 60)

    # For link datasets, validate URL requirement
    if is_link_dataset:
        is_valid, error_msg = validate_link_dataset_annotations(dataset_annotations)
        if not is_valid:
            print(f"❌ Link dataset validation failed: {error_msg}")
            print("\n💡 Link datasets must have a 'url' annotation pointing to the external dataset location")
            sys.exit(1)
        print(f"✓ Link dataset validation passed")
        print(f"  External URL: {dataset_annotations.get('url')}")

    # Validate file annotations
    if not is_link_dataset:
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
    if not dataset_config:
        dataset_config = config.get_dataset_config(args.use_config) if hasattr(args, 'use_config') and args.use_config else {}

    # Debug: Show what config was retrieved
    if config.VERBOSE:
        print(f"\n[DEBUG] Retrieved dataset_config keys: {list(dataset_config.keys())}")
        print(f"[DEBUG] generate_wiki: {dataset_config.get('generate_wiki', False)}")
        print(f"[DEBUG] create_snapshot: {dataset_config.get('create_snapshot', False)}")
        print(f"[DEBUG] create_entity_view: {dataset_config.get('create_entity_view', False)}")

    # ========== PHASE 2: FILE ANNOTATION & VALIDATION ==========
    # SKIP ENTIRELY FOR LINK DATASETS

    if not is_link_dataset:
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

        # Detect dataset type for type-aware columns
        dataset_type_for_view = dataset_annotations.get('_dataset_type', 'ClinicalDataset')
        file_type = dataset_type_for_view.replace('Dataset', 'File')

        view_id = create_dataset_entity_view(
            syn, args.staging_folder, args.dataset_name, config.SYNAPSE_PROJECT_ID,
            file_type, all_schemas,
            dataset_type=dataset_type_for_view,
            dry_run=config.DRY_RUN
        )

        # STEP 3b: Reorder entity view columns (if view was created)
        if view_id and not config.DRY_RUN:
            print("\n" + "=" * 60)
            print("STEP 3b: REORDERING ENTITY VIEW COLUMNS")
            print("=" * 60)

            reorder_entity_view_columns(syn, view_id, dataset_type_for_view, config.DRY_RUN)

        # STEP 3c: Verify entity view columns (if verbose and view was created)
        if view_id and not config.DRY_RUN and config.VERBOSE:
            print("\n" + "=" * 60)
            print("STEP 3c: VERIFYING ENTITY VIEW COLUMNS")
            print("=" * 60)

            verify_entity_view_columns(syn, view_id, config.VERBOSE)

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
        apply_version = dataset_config.get('apply_version', True) if dataset_config else True
        version_label = (dataset_config.get('version_label') if dataset_config else (args.version_label if hasattr(args, 'version_label') and args.version_label else None)) if apply_version else None
        version_comment = dataset_config.get('version_comment') if dataset_config else (args.version_comment if hasattr(args, 'version_comment') and args.version_comment else None)
        if config.VERBOSE:
            print(f"[DEBUG] version_label: {version_label}, version_comment: {version_comment}")
        if version_label:
            print("\n" + "=" * 60)
            print("STEP 4: SETTING FILE VERSION LABELS")
            print("=" * 60)
            success, errors = set_file_versions(syn, file_ids, version_label, version_comment, config.DRY_RUN, config.VERBOSE)
            print(f"✓ Versioned: {success}, Errors: {errors}")
    else:
        print("\n" + "=" * 60)
        print("PHASE 2: SKIPPING FILE OPERATIONS (Link Dataset)")
        print("=" * 60)
        print("🔗 Link datasets do not contain files")
        file_ids = []
        file_type = dataset_annotations.get('_dataset_type', 'ClinicalDataset').replace('Dataset', 'File')

    # ========== PHASE 3: DATASET CREATION & FINALIZATION ==========

    print("\n" + "=" * 60)
    print("PHASE 3: DATASET CREATION & FINALIZATION")
    print("=" * 60)

    # STEP 5: Create dataset entity
    print("\n" + "=" * 60)
    print("STEP 5: CREATING DATASET ENTITY")
    print("=" * 60)

    entity_description = dataset_config.get('description') if dataset_config else None
    dataset_id = create_dataset_entity(
        syn, args.dataset_name, dataset_annotations,
        config.SYNAPSE_PROJECT_ID, all_schemas, config.DRY_RUN,
        description=entity_description
    )

    if not dataset_id:
        print("❌ Failed to create dataset")
        sys.exit(1)

    # STEP 6: Add files to dataset (SKIP FOR LINK DATASETS)
    if not is_link_dataset:
        print("\n" + "=" * 60)
        print("STEP 6: ADDING FILES TO DATASET")
        print("=" * 60)
        add_files_to_dataset(syn, dataset_id, file_ids, config.DRY_RUN)
    else:
        print("\n" + "=" * 60)
        print("STEP 6: SKIPPING FILE ADDITION (Link Dataset)")
        print("=" * 60)
        print("🔗 No files to add")

    # STEP 7: Add columns for faceted search (SKIP FOR LINK DATASETS)
    if not is_link_dataset:
        print("\n" + "=" * 60)
        print("STEP 7: ADDING DATASET COLUMNS")
        print("=" * 60)

        # Detect dataset type from annotations
        dataset_type_for_columns = dataset_annotations.get('_dataset_type')
        if not dataset_type_for_columns:
            dataset_type_for_columns = detect_dataset_type(
                args.dataset_name,
                args.staging_folder if not is_link_dataset else None,
                dataset_config
            )

        # Add columns with type awareness and size constraints
        extra_columns = dataset_config.get('columns', []) if dataset_config else []
        add_dataset_columns(
            syn, dataset_id, all_schemas, file_type,
            dataset_type=dataset_type_for_columns,
            extra_columns=extra_columns,
            dry_run=config.DRY_RUN
        )
    else:
        print("\n" + "=" * 60)
        print("STEP 7: SKIPPING DATASET COLUMNS (Link Dataset)")
        print("=" * 60)
        print("🔗 No files for faceted search")

    # STEP 7b: Reorder dataset columns (SKIP FOR LINK DATASETS)
    # This happens automatically for better UX
    if not is_link_dataset:
        print("\n" + "=" * 60)
        print("STEP 7b: REORDERING DATASET COLUMNS")
        print("=" * 60)

        # Use same dataset type as column addition
        dataset_type_for_columns = dataset_annotations.get('_dataset_type')
        if not dataset_type_for_columns:
            dataset_type_for_columns = detect_dataset_type(
                args.dataset_name,
                args.staging_folder if not is_link_dataset else None,
                dataset_config
            )

        reorder_dataset_columns(syn, dataset_id, dataset_type_for_columns, config.DRY_RUN)

    # STEP 7c: Verify dataset columns (SKIP FOR LINK DATASETS)
    if config.VERBOSE and not is_link_dataset:
        print("\n" + "=" * 60)
        print("STEP 7c: VERIFYING DATASET COLUMNS")
        print("=" * 60)

        verify_dataset_columns(syn, dataset_id, config.VERBOSE)

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

        # Get file list for AI context (empty for link datasets)
        file_list = [list(file_data.keys())[0] for file_data in file_annotations.values()] if not is_link_dataset else []

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

    # STEP 10: Create dataset snapshot (if requested) - SKIP FOR LINK DATASETS (requires files)
    create_snapshot = dataset_config.get('create_snapshot', False) if dataset_config else (args.create_snapshot if hasattr(args, 'create_snapshot') else False)
    version_label = dataset_config.get('version_label') if dataset_config else (args.version_label if hasattr(args, 'version_label') and args.version_label else None)
    version_comment = dataset_config.get('version_comment') if dataset_config else (args.version_comment if hasattr(args, 'version_comment') and args.version_comment else None)
    if config.VERBOSE:
        print(f"[DEBUG] create_snapshot condition: {create_snapshot}, version_label: {version_label}")
    if not is_link_dataset and create_snapshot and version_label:
        print("\n" + "=" * 60)
        print("STEP 10: CREATING DATASET SNAPSHOT")
        print("=" * 60)
        snapshot_version = create_dataset_snapshot(syn, dataset_id, version_label, version_comment, config.DRY_RUN)
        if snapshot_version:
            print(f"✓ Snapshot version: {snapshot_version}")
    elif is_link_dataset and create_snapshot:
        print("\n" + "=" * 60)
        print("STEP 10: SKIPPING DATASET SNAPSHOT (Link Dataset)")
        print("=" * 60)
        print("🔗 Dataset snapshots require files - not supported for link datasets")

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

    # STEP 12: Move files to release folder (SKIP FOR LINK DATASETS)
    # This is the FINAL step and should only be done when user is confident
    if not is_link_dataset:
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
    else:
        print("\n" + "=" * 60)
        print("STEP 12: SKIPPING FILE MOVE (Link Dataset)")
        print("=" * 60)
        print("🔗 No files to move")

    # Summary
    print("\n" + "=" * 60)
    print("✅ CREATE WORKFLOW COMPLETE")
    print("=" * 60)
    print(f"Dataset: {args.dataset_name} ({dataset_id})")
    if is_link_dataset:
        print(f"Type: Link Dataset (no files)")
        print(f"External URL: {dataset_annotations.get('url', 'NOT SET')}")
    else:
        print(f"Files: {len(file_ids)}")
        print(f"Staging Folder: {args.staging_folder}")
        release_folder = dataset_config.get('release_folder') if dataset_config else (args.release_folder if hasattr(args, 'release_folder') and args.release_folder else None)
        auto_move_to_release = dataset_config.get('auto_move_to_release', False)
        if release_folder and auto_move_to_release:
            print(f"Release Folder: {release_folder} (files moved)")
        elif release_folder:
            print(f"Release Folder: {release_folder} (files NOT moved - set auto_move_to_release: true to enable)")
        if version_label:
            print(f"Version: {version_label}")
        if 'view_id' in locals():
            print(f"Entity View: {view_id}")
    print(f"DRY_RUN: {config.DRY_RUN}")

    if config.DRY_RUN:
        print("\n⚠️  This was a DRY_RUN - no changes made")
        print("Run with --execute to apply changes")


def handle_update_workflow(args, config):
    """Handle UPDATE workflow - update existing dataset with new file versions.

    Phase 1 (no --annotations-file): Generate merged annotation templates.
    Phase 2 (with --annotations-file): Validate, upload, move, apply, verify.
    """
    annotations_file = getattr(args, 'annotations_file', None)
    phase = 2 if annotations_file else 1

    print("\n" + "=" * 60)
    print("WORKFLOW: UPDATE EXISTING DATASET")
    print(f"Phase: {'2 — Apply Updates' if phase == 2 else '1 — Template Generation'}")
    print("=" * 60)

    # Load schemas
    print("\nLoading schemas...")
    all_schemas = get_all_schemas(config.SCHEMA_BASE_PATH, config.VERBOSE)

    # Connect to Synapse
    print("\nConnecting to Synapse...")
    syn = connect_to_synapse(config)

    # Get dataset name for config lookup
    dataset_entity = syn.get(args.dataset_id, downloadFile=False)
    dataset_name = dataset_entity.name
    dataset_config = config.get_dataset_config(dataset_name)
    if dataset_config.get('dataset_type'):
        print(f"Using configured dataset type: {dataset_config['dataset_type']}")

    # ── PHASE 1: TEMPLATE GENERATION ─────────────────────────────────────────
    if phase == 1:
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

        # Step 2c: Extract Form Names from staging files (if staging folder provided)
        form_map = {}        # {lower_clean_name: (staging_syn_id, clean_name)}
        name_map = {}        # {staging_syn_id: clean_name}
        local_path_map = {}  # {staging_syn_id: local_file_path}
        view_map = {}        # {staging_syn_id: view_name (raw staging filename w/o ext)}
        if staging_annotations:
            print("\n" + "=" * 60)
            print("STEP 2c: EXTRACTING FORM NAMES FROM STAGING FILES")
            print("=" * 60)
            import tempfile
            _tmp = tempfile.mkdtemp(prefix='sdm_staging_')
            form_map, name_map, local_path_map, view_map = build_staging_form_map(syn, staging_annotations, _tmp)
            print(f"  Extracted form names for {len(form_map)} staging files")
            for sid, cname in name_map.items():
                print(f"    {list(staging_annotations[sid].keys())[0]} → {cname}")

        # Resolve subject file type (single / multi / auto)
        subject_file_type = (
            getattr(args, 'subject_file_type', None)
            or dataset_config.get('subject_file_type')
            or 'auto'
        )

        # Step 2b: Build / load mapping dict from data dictionary (if provided)
        mapping = None
        data_dict_path = getattr(args, 'data_dict', None) or dataset_config.get('data_dict')
        data_dict_view = getattr(args, 'data_dict_view', None) or dataset_config.get('data_dict_view')
        mapping_path = getattr(args, 'mapping', None) or dataset_config.get('mapping')
        mapping_out = None

        if mapping_path and os.path.exists(mapping_path):
            mapping = load_mapping_dict(mapping_path)
            print(f"  Loaded mapping dict: {mapping_path}  ({len(mapping)} entries)")

        elif data_dict_path:
            print("\n" + "=" * 60)
            print("STEP 2b: BUILDING MAPPING FROM DATA DICTIONARY")
            print("=" * 60)

            if not os.path.exists(data_dict_path):
                print(f"  Warning: Data dictionary not found: {data_dict_path} — skipping")
            else:
                parsed = parse_data_dictionary(data_dict_path, view_name=data_dict_view)
                print(f"  Parsed {len(parsed)} fields from data dictionary"
                      + (f" (view: {data_dict_view})" if data_dict_view else ""))

                new_mapping = build_mapping_from_data_dict(parsed)

                safe_name = re.sub(r'[^\w]', '_', dataset_name)
                mapping_out = os.path.join("mapping", f"{safe_name}.dict")
                os.makedirs("mapping", exist_ok=True)

                if os.path.exists(mapping_out):
                    mapping = merge_into_existing_mapping(mapping_out, new_mapping)
                    print(f"  Merged into existing mapping: {mapping_out}")
                else:
                    mapping = new_mapping
                    print(f"  Generated new mapping: {mapping_out}")

                write_mapping_file(mapping_out, mapping)
                mapping = new_mapping

        # Step 3: Generate merged templates
        print("\n" + "=" * 60)
        print("STEP 3: GENERATING ANNOTATION TEMPLATES")
        print("=" * 60)

        annotations_output = {}
        matched_staging_ids = set()

        # For each existing file, create merged template
        for syn_id, file_data in existing_annotations.items():
            filename = list(file_data.keys())[0]
            old_annot = file_data[filename]

            # Check if there's a staging version (form-name-based match, fallback to syn_id)
            new_annot = {}
            matched_staging_id = None
            if form_map:
                match = form_map.get(_norm_filename_for_match(filename))
                if match:
                    matched_staging_id, _ = match
                    new_annot = list(staging_annotations[matched_staging_id].values())[0]
            elif syn_id in staging_annotations:  # fallback: direct syn_id match
                matched_staging_id = syn_id
                new_annot = list(staging_annotations[syn_id].values())[0]

            # Get file type and create template
            file_type = old_annot.get('_file_type') or detect_file_type(
                filename, all_schemas=all_schemas, dataset_config=dataset_config
            )
            template = create_annotation_template(all_schemas, file_type)

            # Priority merge: old > new > template
            merged = merge_file_annotations_priority(old_annot, new_annot, template)

            # Normalize existing annotation values through mapping (if available)
            if mapping:
                merged = normalize_annotations_from_mapping(merged, mapping)

            # Fill empty annotation slots from the actual file contents (unique values per column)
            if mapping and matched_staging_id:
                local_path = local_path_map.get(matched_staging_id)
                if local_path and os.path.exists(local_path):
                    effective_type = subject_file_type
                    if effective_type == 'auto':
                        subj_col = merged.get('subjectIdColumn')
                        if isinstance(subj_col, list):
                            subj_col = subj_col[0] if subj_col else None
                        effective_type = detect_subject_file_type(local_path, subj_col)
                    if effective_type == 'multi':
                        merged = fill_template_from_file_contents(merged, local_path, mapping)
                # Apply view-level annotations from _views
                # Prefer viewName already stored in annotations; fall back to raw staging filename
                view_name = merged.get('viewName')
                if isinstance(view_name, list):
                    view_name = view_name[0] if view_name else None
                if not view_name and matched_staging_id:
                    view_name = view_map.get(matched_staging_id)
                if view_name:
                    merged = apply_view_annotations(merged, view_name, mapping)

            if matched_staging_id and matched_staging_id != syn_id:
                merged['_staging_id'] = matched_staging_id
            if matched_staging_id:
                matched_staging_ids.add(matched_staging_id)

            annotations_output[syn_id] = {filename: merged}

        # Add unmatched staging files as new entries (form name as filename, empty template)
        for staging_syn_id, file_data in staging_annotations.items():
            if staging_syn_id in matched_staging_ids:
                continue
            clean_name = name_map.get(staging_syn_id, list(file_data.keys())[0])
            file_type = detect_file_type(clean_name, all_schemas=all_schemas, dataset_config=dataset_config)
            template = create_annotation_template(all_schemas, file_type)
            template['_staging_id'] = staging_syn_id

            # Fill from file contents for new files too
            if mapping:
                local_path = local_path_map.get(staging_syn_id)
                if local_path and os.path.exists(local_path):
                    effective_type = subject_file_type
                    if effective_type == 'auto':
                        subj_col = template.get('subjectIdColumn')
                        if isinstance(subj_col, list):
                            subj_col = subj_col[0] if subj_col else None
                        effective_type = detect_subject_file_type(local_path, subj_col)
                    if effective_type == 'multi':
                        template = fill_template_from_file_contents(template, local_path, mapping)
                # Apply view-level annotations from _views using raw staging filename as view name
                view_name = view_map.get(staging_syn_id)
                if view_name and mapping:
                    template = apply_view_annotations(template, view_name, mapping)

            annotations_output[staging_syn_id] = {clean_name: template}
            print(f"  + New file (no existing match): {clean_name} ({staging_syn_id})")

        # Save annotations
        output_file = os.path.join(config.ANNOTATIONS_DIR, f"{dataset_name}_update_annotations.json")
        save_annotation_file(annotations_output, output_file)

        print("\n" + "=" * 60)
        print("✅ PHASE 1 COMPLETE — Template generated")
        print("=" * 60)
        print(f"Annotations saved to: {output_file}")
        print(f"Total files        : {len(annotations_output)}")
        if mapping_out:
            print(f"Mapping file       : {mapping_out}")
        print("\n⚠️  MANUAL STEP: Edit the annotation file, then re-run with:")
        print(f"  python synapse_dataset_manager.py update \\")
        print(f"    --dataset-id {args.dataset_id} \\")
        print(f"    --annotations-file {output_file} \\")
        print(f"    --execute")
        return

    # ── PHASE 2: APPLY UPDATES ────────────────────────────────────────────────

    # Resolve optional Phase 2 args (may come from CLI or config)
    local_files_dir = getattr(args, 'local_files_dir', None)
    release_folder = getattr(args, 'release_folder', None) or dataset_config.get('release_folder')
    apply_version = dataset_config.get('apply_version', True) if dataset_config else True
    version_label = (getattr(args, 'version_label', None) or dataset_config.get('version_label')) if apply_version else None
    version_comment = getattr(args, 'version_comment', None) or dataset_config.get('version_comment')
    skip_validation = getattr(args, 'skip_validation', False)

    # Step 1: Load annotations
    print("\n" + "=" * 60)
    print("STEP 1: LOADING ANNOTATIONS FILE")
    print("=" * 60)

    if not os.path.exists(annotations_file):
        print(f"❌ Error: Annotations file not found: {annotations_file}")
        sys.exit(1)

    with open(annotations_file) as f:
        file_annotations = json.load(f)
    print(f"✓ Loaded {len(file_annotations)} file entries from {annotations_file}")

    # Step 2: Validate annotations
    if not skip_validation:
        print("\n" + "=" * 60)
        print("STEP 2: VALIDATING ANNOTATIONS")
        print("=" * 60)

        validation_errors = False
        for syn_id, file_data in file_annotations.items():
            filename = list(file_data.keys())[0]
            annots = file_data[filename]
            file_type = annots.get('_file_type', 'File')
            is_valid, errors, warnings = validate_annotation_against_schema(annots, file_type, all_schemas)
            for w in warnings:
                print(f"  ⚠ {filename}: {w}")
            if errors:
                for e in errors:
                    print(f"  ✗ {filename}: {e}")
                validation_errors = True

        if validation_errors:
            print("\n❌ Validation errors found. Fix them or re-run with --skip-validation.")
            sys.exit(1)
        else:
            print("✓ All annotations valid")
    else:
        print("\n⚠️  Skipping annotation validation (--skip-validation)")

    # Retrieve existing annotations to detect "new" vs "existing" files
    existing_annotations = enumerate_dataset_files(syn, args.dataset_id, config.VERBOSE)
    existing_ids = set(existing_annotations.keys())

    # Identify new files (in annotations but not in existing dataset)
    new_file_ids_annotations = {
        syn_id: data for syn_id, data in file_annotations.items()
        if syn_id not in existing_ids
    }
    existing_file_ids_annotations = {
        syn_id: data for syn_id, data in file_annotations.items()
        if syn_id in existing_ids
    }

    if new_file_ids_annotations:
        print(f"\n  New files (not yet in dataset): {len(new_file_ids_annotations)}")
    print(f"  Existing files to update      : {len(existing_file_ids_annotations)}")

    # Step 3a: Upload new versions from staging (files with _staging_id)
    staging_to_upload = {
        sid: data for sid, data in existing_file_ids_annotations.items()
        if list(data.values())[0].get('_staging_id')
    }
    if staging_to_upload:
        print("\n" + "=" * 60)
        print("STEP 3a: UPLOADING NEW VERSIONS FROM STAGING")
        print("=" * 60)
        uploaded, upload_errors, skipped = upload_new_versions_from_staging(
            syn, staging_to_upload,
            version_label=version_label,
            version_comment=version_comment,
            dry_run=config.DRY_RUN,
            verbose=config.VERBOSE
        )
        print(f"  Uploaded: {uploaded}, Errors: {upload_errors}, Skipped: {skipped}")

    # Step 3: Upload new file versions from local dir (if provided)
    if local_files_dir:
        print("\n" + "=" * 60)
        print("STEP 3: UPLOADING NEW FILE VERSIONS")
        print("=" * 60)
        print(f"Local files dir: {local_files_dir}")
        if version_label:
            print(f"Version label  : {version_label}")

        uploaded, upload_errors, skipped = upload_file_new_versions(
            syn, existing_file_ids_annotations, local_files_dir,
            version_label=version_label,
            version_comment=version_comment,
            dry_run=config.DRY_RUN,
            verbose=config.VERBOSE
        )
        print(f"\n  Uploaded: {uploaded}, Errors: {upload_errors}, Skipped (no local file): {skipped}")
    else:
        print("\n" + "=" * 60)
        print("STEP 3: SKIPPING UPLOAD (no --local-files-dir)")
        print("=" * 60)

        # Apply annotations (and optionally force-version) for files not handled by staging upload
        no_staging_files = {
            sid: data for sid, data in existing_file_ids_annotations.items()
            if not list(data.values())[0].get('_staging_id')
        }
        if no_staging_files:
            label_str = f" (forcing version '{version_label}')" if version_label else ""
            print(f"Applying annotations to {len(no_staging_files)} files without staging upload{label_str}...")
            success_count, error_count = apply_annotations_to_files(
                syn, no_staging_files,
                dry_run=config.DRY_RUN, verbose=config.VERBOSE,
                version_label=version_label,
                version_comment=version_comment,
            )
            print(f"\n  Applied: {success_count}, Errors: {error_count}")

    # Step 4: Move new-only staging files to release folder
    if new_file_ids_annotations and release_folder:
        print("\n" + "=" * 60)
        print("STEP 4: MOVING NEW FILES TO RELEASE FOLDER")
        print("=" * 60)
        print(f"New files : {len(new_file_ids_annotations)}")
        print(f"Release folder: {release_folder}")

        moved, move_errors = move_and_add_new_files(
            syn, new_file_ids_annotations,
            release_folder_id=release_folder,
            dataset_id=args.dataset_id,
            dry_run=config.DRY_RUN,
            verbose=config.VERBOSE,
            version_label=version_label,
            version_comment=version_comment,
        )
        print(f"\n  Moved & added: {moved}, Errors: {move_errors}")
    elif new_file_ids_annotations and not release_folder:
        print("\n" + "=" * 60)
        print("STEP 4: SKIPPING MOVE (no --release-folder)")
        print("=" * 60)
        print(f"⚠️  {len(new_file_ids_annotations)} new files found but --release-folder not set.")
        print("    Provide --release-folder to move them to the release folder and add to dataset.")
    else:
        print("\n" + "=" * 60)
        print("STEP 4: NO NEW FILES TO MOVE")
        print("=" * 60)

    # Step 5: Verify results
    print("\n" + "=" * 60)
    print("STEP 5: VERIFYING RESULTS")
    print("=" * 60)

    if config.DRY_RUN:
        print("⚠️  DRY RUN — skipping live verification")
    else:
        all_ids = list(file_annotations.keys())
        verify_update_results(
            syn, args.dataset_id, all_ids,
            expected_version_label=version_label,
            release_folder_id=release_folder,
            verbose=config.VERBOSE
        )

    print("\n" + "=" * 60)
    if config.DRY_RUN:
        print("✅ PHASE 2 DRY RUN COMPLETE — re-run with --execute to apply changes")
    else:
        print("✅ PHASE 2 COMPLETE — Update applied")
    print("=" * 60)


def handle_annotate_dataset(args, config):
    """Handle ANNOTATE-DATASET workflow — push annotations to an existing dataset entity"""
    print("\n" + "=" * 60)
    print("WORKFLOW: ANNOTATE EXISTING DATASET")
    print("=" * 60)

    print("\nLoading schemas...")
    all_schemas = get_all_schemas(config.SCHEMA_BASE_PATH, config.VERBOSE)

    if not os.path.exists(args.annotations_file):
        print(f"❌ Error: Annotations file not found: {args.annotations_file}")
        sys.exit(1)

    with open(args.annotations_file) as f:
        annotations = json.load(f)
    print(f"✓ Loaded annotations from {args.annotations_file}")

    print("\nConnecting to Synapse...")
    syn = connect_to_synapse(config)

    try:
        entity = syn.get(args.dataset_id, downloadFile=False)
        print(f"✓ Found dataset: {entity.name} ({args.dataset_id})")
    except Exception as e:
        print(f"❌ Error: Could not retrieve dataset {args.dataset_id}: {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("APPLYING DATASET ANNOTATIONS")
    print("=" * 60)

    success = apply_dataset_annotations(
        syn, args.dataset_id, annotations, all_schemas, dry_run=config.DRY_RUN
    )

    print("\n" + "=" * 60)
    if success:
        if config.DRY_RUN:
            print("✅ DRY RUN COMPLETE — re-run with --execute to apply")
        else:
            print("✅ DATASET ANNOTATIONS APPLIED SUCCESSFULLY")
    else:
        print("❌ FAILED TO APPLY ANNOTATIONS")
        sys.exit(1)
    print("=" * 60)


def handle_generate_mapping(args, config):
    ignore_cols = {"subject_id"} | set(getattr(args, "ignore", None) or [])
    max_values = getattr(args, "max_values", 50)

    input_path = Path(args.input)
    if input_path.is_dir():
        supported = {".csv", ".xlsx", ".xls"}
        paths = sorted(p for p in input_path.iterdir()
                       if p.suffix.lower() in supported)
        print(f"Found {len(paths)} metadata file(s) in {input_path}")
    elif input_path.is_file():
        paths = [input_path]
    else:
        print(f"ERROR: --input path not found: {args.input}")
        sys.exit(1)

    if not paths:
        print("ERROR: No supported metadata files found (.csv, .xlsx, .xls)")
        sys.exit(1)

    unique_vals = collect_unique_values(paths, ignore_cols, max_values)
    print(f"\n  {len(unique_vals)} columns found "
          f"({sum(1 for v in unique_vals.values() if v is not None)} with value mappings, "
          f"{sum(1 for v in unique_vals.values() if v is None)} without)")

    new_mapping = build_mapping_dict(unique_vals)

    output_path = args.output
    if os.path.exists(output_path):
        print(f"\nUpdating existing mapping file: {output_path}")
        mapping = merge_into_existing_mapping(output_path, new_mapping)
    else:
        mapping = new_mapping

    write_mapping_file(output_path, mapping)


def handle_set_version(args, config):
    """Apply version labels to all files in a dataset and optionally create a snapshot."""
    syn = connect_to_synapse(config)

    version_label = args.version_label
    version_comment = getattr(args, 'version_comment', None)
    create_snapshot = getattr(args, 'create_snapshot', False)
    description = getattr(args, 'description', None)

    # Step 1: Get file IDs from dataset
    print("\n" + "=" * 60)
    print("STEP 1: RETRIEVING DATASET FILES")
    print("=" * 60)
    file_annotations = enumerate_dataset_files(syn, args.dataset_id, config.VERBOSE)
    file_ids = list(file_annotations.keys())
    print(f"✓ Found {len(file_ids)} files")

    # Step 2: Set version labels on files
    print("\n" + "=" * 60)
    print("STEP 2: SETTING FILE VERSION LABELS")
    print("=" * 60)
    success, errors = set_file_versions(
        syn, file_ids, version_label, version_comment,
        dry_run=config.DRY_RUN, verbose=config.VERBOSE
    )
    print(f"✓ Versioned: {success}, Errors: {errors}")

    # Step 3: Set dataset entity description (optional)
    if description:
        print("\n" + "=" * 60)
        print("STEP 3: SETTING DATASET DESCRIPTION")
        print("=" * 60)
        if config.DRY_RUN:
            print(f"  [DRY_RUN] Would set description on {args.dataset_id}:")
            print(f"  [DRY_RUN] {description[:120]}{'...' if len(description) > 120 else ''}")
        else:
            try:
                entity = syn.get(args.dataset_id, downloadFile=False)
                entity.description = description
                syn.store(entity)
                print(f"  ✓ Description set on {args.dataset_id}")
            except Exception as e:
                print(f"  ✗ Error setting description: {e}")

    # Step 4: Create dataset snapshot (optional)
    if create_snapshot:
        print("\n" + "=" * 60)
        print("STEP 4: CREATING DATASET SNAPSHOT")
        print("=" * 60)
        snapshot_version = create_dataset_snapshot(
            syn, args.dataset_id, version_label, version_comment, config.DRY_RUN
        )
        if snapshot_version:
            print(f"✓ Snapshot version: {snapshot_version}")
    else:
        print("\n💡 Tip: Re-run with --create-snapshot (or set create_snapshot: true in config) to also snapshot the dataset.")


def handle_delete_versions_workflow(args, config):
    """
    Delete file versions by label across a single entity or all files in a dataset.

    Supports:
      --syn-id          single entity to target
      --dataset-id      delete matching versions from every file in this dataset
      --use-config      load dataset_id (and optionally version-label list) from config
      --version-label   one or more labels to delete
    """
    syn = synapseclient.Synapse()
    syn.login(silent=True)

    version_labels = getattr(args, 'version_label', None) or []
    if not version_labels:
        print("❌ No --version-label provided. Nothing to do.")
        return

    dataset_config = {}
    if hasattr(args, 'use_config') and args.use_config:
        dataset_config = config.get_dataset_config(args.use_config) or {}
        if not dataset_config:
            print(f"❌ Config '{args.use_config}' not found.")
            return

    # Resolve dataset_id or syn_id
    dataset_id = getattr(args, 'dataset_id', None) or dataset_config.get('dataset_id')
    single_syn_id = getattr(args, 'syn_id', None)

    if not dataset_id and not single_syn_id:
        print("❌ Provide --dataset-id, --syn-id, or --use-config with a dataset_id.")
        return

    dry_run = config.DRY_RUN
    if getattr(args, 'execute', False):
        dry_run = False
    if getattr(args, 'dry_run', False):
        dry_run = True

    mode = "[DRY RUN]" if dry_run else "[EXECUTE]"
    print(f"\n{'='*60}")
    print(f"DELETE FILE VERSIONS {mode}")
    print(f"{'='*60}")
    print(f"Labels to delete : {version_labels}")

    total_deleted = total_skipped = total_errors = 0

    def _process_file_list(file_ids_names):
        nonlocal total_deleted, total_skipped, total_errors
        for fid, fname in file_ids_names:
            print(f"  [{fid}] {fname}")
            d, s, e = delete_file_versions_by_label(syn, fid, version_labels,
                                                     dry_run=dry_run,
                                                     verbose=config.VERBOSE)
            total_deleted += d; total_skipped += s; total_errors += e

    if single_syn_id:
        # Auto-detect entity type
        entity = syn.get(single_syn_id, downloadFile=False)
        concrete_type = entity.get('concreteType', '')

        if 'FileEntity' in concrete_type:
            # Single file
            print(f"Target (file)    : {single_syn_id} ({entity.name})")
            d, s, e = delete_file_versions_by_label(syn, single_syn_id, version_labels,
                                                     dry_run=dry_run, verbose=True)
            total_deleted += d; total_skipped += s; total_errors += e

        elif 'Folder' in concrete_type or 'Project' in concrete_type:
            # Enumerate all files in the folder (non-recursive, direct children)
            print(f"Target (folder)  : {single_syn_id} ({entity.name})")
            children = list(syn.getChildren(single_syn_id, includeTypes=['file']))
            print(f"Files in folder  : {len(children)}\n")
            _process_file_list([(c['id'], c['name']) for c in children])

        elif 'Dataset' in concrete_type:
            # Enumerate via table query
            print(f"Target (dataset) : {single_syn_id} ({entity.name})")
            try:
                results = syn.tableQuery(
                    f"SELECT id, name FROM {single_syn_id}", includeRowIdAndRowVersion=False
                )
                file_rows = results.asDataFrame()
                print(f"Files in dataset : {len(file_rows)}\n")
                _process_file_list(
                    [(row.get('id') or row.iloc[0], row.get('name', '')) for _, row in file_rows.iterrows()]
                )
            except Exception as e:
                print(f"❌ Could not query dataset {single_syn_id}: {e}")
                return
        else:
            print(f"❌ Unsupported entity type '{concrete_type}' for {single_syn_id}")
            return

    elif dataset_id:
        print(f"Dataset          : {dataset_id}")
        try:
            results = syn.tableQuery(
                f"SELECT id, name FROM {dataset_id}", includeRowIdAndRowVersion=False
            )
            file_rows = results.asDataFrame()
        except Exception as e:
            print(f"❌ Could not query dataset {dataset_id}: {e}")
            return

        print(f"Files in dataset : {len(file_rows)}\n")
        _process_file_list(
            [(row.get('id') or row.iloc[0], row.get('name', '')) for _, row in file_rows.iterrows()]
        )

    print(f"\n{'='*60}")
    print(f"Summary: deleted={total_deleted}, skipped={total_skipped}, errors={total_errors}")
    if dry_run:
        print("Re-run with --execute to apply deletions.")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Synapse Dataset Manager - Create or update datasets',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # GENERATE TEMPLATE - Create empty dataset annotation template
  python synapse_dataset_manager.py generate-template --type Clinical
  python synapse_dataset_manager.py generate-template --type Omic --output my_template.json

  # ADD LINK FILE - Create link file entity (external URL reference)
  python synapse_dataset_manager.py add-link-file \\
    --name "GEO Dataset" \\
    --url "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE12345" \\
    --dataset-id syn67890 \\
    --annotations '{"dataType": "transcriptomics"}' \\
    --execute

  # CREATE workflow - using config.yaml settings
  python synapse_dataset_manager.py create --use-config GEN_PIPELINE_TEST

  # CREATE workflow - with manual arguments
  python synapse_dataset_manager.py create \\
    --project-id syn11111111 \\
    --staging-folder syn12345 \\
    --dataset-name "My New Dataset"

  # CREATE workflow - link dataset (no files)
  python synapse_dataset_manager.py create --link-dataset \\
    --dataset-name "External GEO Dataset"

  # CREATE workflow - apply annotations (using config)
  python synapse_dataset_manager.py create --use-config GEN_PIPELINE_TEST \\
    --from-annotations --execute

  # CREATE workflow - apply annotations (manual)
  python synapse_dataset_manager.py create --from-annotations \\
    --staging-folder syn12345 \\
    --dataset-name "My New Dataset" \\
    --execute

  # UPDATE workflow - Phase 1: generate templates (via config)
  python synapse_dataset_manager.py update --use-config ALL_ALS_ASSESS

  # UPDATE workflow - Phase 1: generate templates (explicit args)
  python synapse_dataset_manager.py update \\
    --dataset-id syn67890 \\
    --staging-folder syn12345

  # UPDATE workflow - Phase 2: apply updates (via config, after editing annotations JSON)
  python synapse_dataset_manager.py update --use-config ALL_ALS_ASSESS --execute

  # UPDATE workflow - Phase 2: upload new file versions from local dir
  python synapse_dataset_manager.py update \\
    --dataset-id syn67890 \\
    --annotations-file annotations/DatasetName_update_annotations.json \\
    --local-files-dir staging/assess/ \\
    --version-label "v4-JAN" \\
    --version-comment "January 2026 release" \\
    --execute

  # UPDATE workflow - Phase 2: move new staging files to release + apply annotations
  python synapse_dataset_manager.py update \\
    --dataset-id syn67890 \\
    --staging-folder syn12345 \\
    --release-folder syn68885185 \\
    --annotations-file annotations/DatasetName_update_annotations.json \\
    --version-label "v4-JAN" \\
    --execute

  # Use custom config file
  python synapse_dataset_manager.py --config my-config.yaml create --use-config my_dataset

  # ANNOTATE-DATASET - push annotations from file to existing dataset entity
  python synapse_dataset_manager.py annotate-dataset \\
    --dataset-id syn12345 \\
    --annotations-file annotations/all_als/assess_dataset_annotations.json \\
    --execute
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
    create_parser.add_argument('--project-id',
                              help='Synapse project ID where dataset will be created (overrides config)')
    create_parser.add_argument('--staging-folder',
                              help='Synapse ID of staging folder containing files')
    create_parser.add_argument('--dataset-name',
                              help='Name for the new dataset')
    create_parser.add_argument('--from-annotations', action='store_true',
                              help='Skip template generation, use existing annotations')
    create_parser.add_argument('--link-dataset', action='store_true',
                              help='Create link dataset (no files, external URL reference only)')
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
    update_parser.add_argument('--use-config',
                              help='Load update settings from config.yaml datasets section (e.g., "ALL_ALS_ASSESS")')
    update_parser.add_argument('--dataset-id',
                              help='Synapse ID of existing dataset (required unless --use-config provides it)')
    update_parser.add_argument('--staging-folder',
                              help='Synapse ID of staging folder with new files (optional)')
    update_parser.add_argument('--annotations-file',
                              help='Path to pre-edited annotations JSON (triggers Phase 2 apply)')
    update_parser.add_argument('--local-files-dir',
                              help='Local directory containing prepared file versions to upload as new versions')
    update_parser.add_argument('--release-folder',
                              help='Synapse ID of release folder (for moving new staging files)')
    update_parser.add_argument('--version-label',
                              help='Version label for new file versions (e.g., "v4-JAN")')
    update_parser.add_argument('--version-comment',
                              help='Version comment for new file versions')
    update_parser.add_argument('--skip-validation', action='store_true',
                              help='Skip annotation schema validation before applying')
    update_parser.add_argument('--data-dict',
                              help='Path to data dictionary CSV/XLSX (View Name, Field, Description, Values)')
    update_parser.add_argument('--data-dict-view',
                              help='View Name to filter from data dictionary (e.g. "ASSESS")')
    update_parser.add_argument('--mapping',
                              help='Path to existing mapping .dict file (overrides --data-dict)')
    update_parser.add_argument('--subject-file-type',
                              choices=['single', 'multi', 'auto'],
                              default=None,
                              help=(
                                  'How to treat files when filling annotations from file contents. '
                                  '"single": one subject per file (no file-content filling). '
                                  '"multi": multiple subjects per file (collect unique values per column). '
                                  '"auto" (default): detect per file using the subject ID column.'
                              ))
    update_parser.add_argument('--execute', action='store_true',
                              help='Execute (override DRY_RUN)')
    update_parser.add_argument('--dry-run', action='store_true',
                              help='Dry run mode')

    # ANNOTATE-DATASET command
    annotate_parser = subparsers.add_parser(
        'annotate-dataset',
        help='Apply annotations from a JSON file to an existing dataset entity'
    )
    annotate_parser.add_argument('--dataset-id', required=True,
                                 help='Synapse ID of existing dataset entity')
    annotate_parser.add_argument('--annotations-file', required=True,
                                 help='Path to JSON annotations file')
    annotate_parser.add_argument('--execute', action='store_true',
                                 help='Execute (override DRY_RUN)')
    annotate_parser.add_argument('--dry-run', action='store_true',
                                 help='Dry run mode (default)')

    # GENERATE-TEMPLATE command
    template_parser = subparsers.add_parser('generate-template',
                                           help='Generate empty dataset annotation template')
    template_parser.add_argument('--type', '-t',
                                choices=['Clinical', 'Omic', 'Dataset'],
                                default='Dataset',
                                help='Dataset type (default: Dataset)')
    template_parser.add_argument('--output', '-o',
                                help='Output file path (default: annotations/<type>_dataset_template.json)')

    # GENERATE-FILE-TEMPLATES command
    file_tmpl_parser = subparsers.add_parser(
        'generate-file-templates',
        help='Generate per-file annotation templates from a Synapse folder'
    )
    file_tmpl_parser.add_argument('--folder', required=True,
        help='Synapse ID of folder containing files (e.g., syn12345)')
    file_tmpl_parser.add_argument('--name', default=None,
        help='Name prefix for output file (default: folder syn ID)')
    file_tmpl_parser.add_argument('--type', choices=['Clinical', 'Omic', 'File'], default=None,
        help='Override file type for all files instead of auto-detecting')
    file_tmpl_parser.add_argument('--output', '-o', default=None,
        help='Output JSON file path (default: annotations/<name>_file_templates.json)')
    file_tmpl_parser.add_argument('--skip-ai', action='store_true',
        help='Skip AI-assisted annotation enhancement')
    file_tmpl_parser.add_argument('--mapping', default=None,
        help='Path to field mapping dict file (e.g., mapping/target_als.dict)')
    file_tmpl_parser.add_argument('--metadata', nargs='+', default=None,
        help='One or more source metadata CSV/XLSX files (space-separated)')
    file_tmpl_parser.add_argument('--refresh-walkthrough', action='store_true',
        help='Re-enumerate Synapse folder even if walkthrough cache exists')

    # APPLY-FILE-ANNOTATIONS command
    apply_file_parser = subparsers.add_parser(
        'apply-file-annotations',
        help='Apply edited per-file annotation JSON to Synapse file entities'
    )
    apply_file_parser.add_argument('--annotations-file', required=True,
        help='Path to per-file annotations JSON (e.g., annotations/my_dataset_file_templates.json)')
    apply_file_parser.add_argument('--execute', action='store_true',
        help='Execute (override DRY_RUN — actually write to Synapse)')
    apply_file_parser.add_argument('--dry-run', action='store_true',
        help='Dry run mode (default — prints what would be applied)')
    apply_file_parser.add_argument('--skip-validation', action='store_true',
        help='Skip schema validation before applying annotations')

    # ADD-LINK-FILE command
    link_parser = subparsers.add_parser('add-link-file',
                                       help='Create link file entity (external URL reference) and add to dataset')
    link_parser.add_argument('--name', required=True,
                            help='Name for the link file entity')
    link_parser.add_argument('--url', required=True,
                            help='External URL to reference')
    link_parser.add_argument('--parent-id',
                            help='Parent folder/project ID where link file will be stored (e.g., syn12345)')
    link_parser.add_argument('--dataset-id',
                            help='Dataset ID to add the link to (also sets parent if --parent-id not specified)')
    link_parser.add_argument('--annotations',
                            help='JSON string of annotations (e.g., \'{"dataType": "transcriptomics"}\')')
    link_parser.add_argument('--execute', action='store_true',
                            help='Execute (override DRY_RUN)')
    link_parser.add_argument('--dry-run', action='store_true',
                            help='Dry run mode')

    # GENERATE-MAPPING command
    mapping_parser = subparsers.add_parser(
        'generate-mapping',
        help='Generate a scaffold mapping .dict file from metadata column names and unique values'
    )
    mapping_parser.add_argument('--input', '-i', required=True,
        help='Metadata file (.csv/.xlsx) or folder of metadata files')
    mapping_parser.add_argument('--output', '-o', required=True,
        help='Output mapping .dict file path (created or updated in-place)')
    mapping_parser.add_argument('--ignore', nargs='+', default=None,
        help='Additional columns to exclude beyond subject_id (space-separated)')
    mapping_parser.add_argument('--max-values', type=int, default=50,
        help='Max unique values for a column to get a value-map dict (default: 50)')

    # SET-VERSION command
    version_parser = subparsers.add_parser(
        'set-version',
        help='Apply version labels to all files in an existing dataset and optionally create a snapshot'
    )
    version_parser.add_argument('--use-config',
                                help='Load settings from config.yaml datasets section (e.g., "Target_ALS_Dataset")')
    version_parser.add_argument('--dataset-id',
                                help='Synapse ID of existing dataset (required unless --use-config provides it)')
    version_parser.add_argument('--version-label',
                                help='Version label to apply (e.g., "v1.0", "2026.1"); required unless --use-config provides it')
    version_parser.add_argument('--version-comment',
                                help='Optional comment describing this version')
    version_parser.add_argument('--description',
                                help='Entity description to set on the dataset (visible in Synapse UI)')
    version_parser.add_argument('--create-snapshot', action='store_true',
                                help='Also create a dataset snapshot after labeling files')
    version_parser.add_argument('--execute', action='store_true',
                                help='Execute (override DRY_RUN)')
    version_parser.add_argument('--dry-run', action='store_true',
                                help='Dry run mode (default)')

    # DELETE-VERSIONS command
    delete_parser = subparsers.add_parser(
        'delete-versions',
        help='Delete file versions by version label (single entity or all files in a dataset)'
    )
    delete_parser.add_argument('--use-config',
                               help='Load dataset_id from config.yaml datasets section (e.g., "ALL_ALS_ASSESS")')
    delete_parser.add_argument('--dataset-id',
                               help='Synapse ID of dataset — deletes matching versions from every file in it')
    delete_parser.add_argument('--syn-id',
                               help='Synapse ID to target: file (single entity), folder (enumerates direct children), or dataset (enumerates all files)')
    delete_parser.add_argument('--version-label', nargs='+', metavar='LABEL',
                               help='One or more version labels to delete (e.g. v5-FEB_test v5-FEB_test_v2)')
    delete_parser.add_argument('--execute', action='store_true',
                               help='Execute deletions (default is dry-run)')
    delete_parser.add_argument('--dry-run', action='store_true',
                               help='Dry run mode (default)')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Load config from file
    config = Config(config_file=args.config)

    # Override project ID from CLI if provided
    if args.command == 'create' and hasattr(args, 'project_id') and args.project_id:
        config.SYNAPSE_PROJECT_ID = args.project_id
        print(f"Using project ID from --project-id: {args.project_id}")

    # Handle --use-config: Load dataset settings from config
    if args.command == 'create' and hasattr(args, 'use_config') and args.use_config:
        dataset_config = config.get_dataset_config(args.use_config)
        if not dataset_config:
            print(f"❌ Error: Dataset config '{args.use_config}' not found in config file")
            print(f"\nAvailable configs: {list(config.full_config.get('datasets', {}).keys())}")
            sys.exit(1)

        # Load link_dataset flag from config
        if not hasattr(args, 'link_dataset') or not args.link_dataset:
            if 'link_dataset' in dataset_config and dataset_config['link_dataset']:
                args.link_dataset = True
                print(f"Using link_dataset mode from config: {args.link_dataset}")

        # For link datasets, staging_folder should NOT be loaded from config
        if hasattr(args, 'link_dataset') and args.link_dataset:
            if 'staging_folder' in dataset_config:
                print("⚠️  WARNING: Ignoring staging_folder from config (link dataset mode)")
        else:
            # Load settings from config (only if not provided via CLI and not link dataset)
            if not args.staging_folder and 'staging_folder' in dataset_config:
                args.staging_folder = dataset_config['staging_folder']
                print(f"Using staging_folder from config: {args.staging_folder}")

        if not args.dataset_name and 'dataset_name' in dataset_config:
            args.dataset_name = dataset_config['dataset_name']
            print(f"Using dataset_name from config: {args.dataset_name}")

    # Handle --use-config for update command
    if args.command == 'update' and hasattr(args, 'use_config') and args.use_config:
        dataset_config = config.get_dataset_config(args.use_config)
        if not dataset_config:
            print(f"❌ Error: Dataset config '{args.use_config}' not found in config file")
            print(f"\nAvailable configs: {list(config.full_config.get('datasets', {}).keys())}")
            sys.exit(1)

        # Load update-specific fields from config (CLI args take precedence)
        if not args.dataset_id and 'dataset_id' in dataset_config:
            args.dataset_id = dataset_config['dataset_id']
            print(f"Using dataset_id from config: {args.dataset_id}")

        if not args.staging_folder and 'staging_folder' in dataset_config:
            args.staging_folder = dataset_config['staging_folder']
            print(f"Using staging_folder from config: {args.staging_folder}")

        if not args.release_folder and 'release_folder' in dataset_config:
            args.release_folder = dataset_config['release_folder']
            print(f"Using release_folder from config: {args.release_folder}")

        if not args.version_label and 'version_label' in dataset_config:
            args.version_label = dataset_config['version_label']
            print(f"Using version_label from config: {args.version_label}")

        if not args.version_comment and 'version_comment' in dataset_config:
            args.version_comment = dataset_config['version_comment']
            print(f"Using version_comment from config: {args.version_comment}")

        if not args.local_files_dir and 'local_files_dir' in dataset_config:
            args.local_files_dir = dataset_config['local_files_dir']
            print(f"Using local_files_dir from config: {args.local_files_dir}")

        if not args.annotations_file and 'annotations_file' in dataset_config:
            args.annotations_file = dataset_config['annotations_file']
            print(f"Using annotations_file from config: {args.annotations_file}")

        if not getattr(args, 'data_dict', None) and 'data_dict' in dataset_config:
            args.data_dict = dataset_config['data_dict']
            print(f"Using data_dict from config: {args.data_dict}")

        if not getattr(args, 'data_dict_view', None) and 'data_dict_view' in dataset_config:
            args.data_dict_view = dataset_config['data_dict_view']
            print(f"Using data_dict_view from config: {args.data_dict_view}")

        if not getattr(args, 'mapping', None) and 'mapping' in dataset_config:
            args.mapping = dataset_config['mapping']
            print(f"Using mapping from config: {args.mapping}")

        if not getattr(args, 'subject_file_type', None) and 'subject_file_type' in dataset_config:
            args.subject_file_type = dataset_config['subject_file_type']
            print(f"Using subject_file_type from config: {args.subject_file_type}")

    # Handle --use-config for set-version command
    if args.command == 'set-version' and hasattr(args, 'use_config') and args.use_config:
        dataset_config = config.get_dataset_config(args.use_config)
        if not dataset_config:
            print(f"❌ Error: Dataset config '{args.use_config}' not found in config file")
            print(f"\nAvailable configs: {list(config.full_config.get('datasets', {}).keys())}")
            sys.exit(1)

        if not args.dataset_id and 'dataset_id' in dataset_config:
            args.dataset_id = dataset_config['dataset_id']
            print(f"Using dataset_id from config: {args.dataset_id}")

        if not args.version_label and 'version_label' in dataset_config:
            args.version_label = dataset_config['version_label']
            print(f"Using version_label from config: {args.version_label}")

        if not args.version_comment and 'version_comment' in dataset_config:
            args.version_comment = dataset_config['version_comment']
            print(f"Using version_comment from config: {args.version_comment}")

        if not args.create_snapshot and dataset_config.get('create_snapshot', False):
            args.create_snapshot = True
            print(f"Using create_snapshot from config: {args.create_snapshot}")

        if not args.description and 'description' in dataset_config:
            args.description = dataset_config['description']
            print(f"Using description from config")

    # Validate required arguments for set-version command
    if args.command == 'set-version':
        if not args.dataset_id:
            print("❌ Error: --dataset-id is required (or use --use-config with dataset_id in config)")
            sys.exit(1)
        if not args.version_label:
            print("❌ Error: --version-label is required (or use --use-config with version_label in config)")
            sys.exit(1)

    # Validate required arguments for update command
    if args.command == 'update':
        if not args.dataset_id:
            print("❌ Error: --dataset-id is required (or use --use-config with dataset_id in config)")
            sys.exit(1)

    # Validate required arguments for create command
    if args.command == 'create':
        # Validate link dataset requirements
        if hasattr(args, 'link_dataset') and args.link_dataset:
            if args.staging_folder:
                print("❌ Error: --staging-folder cannot be used with --link-dataset")
                print("   Link datasets reference external URLs and do not contain files")
                sys.exit(1)
        else:
            # Only require staging folder for non-link datasets
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

    # Handle execute/dry-run for add-link-file command
    if args.command == 'add-link-file':
        if hasattr(args, 'execute') and args.execute:
            config.DRY_RUN = False
        if hasattr(args, 'dry_run') and args.dry_run:
            config.DRY_RUN = True

    # Only validate config for commands that need Synapse connection
    if args.command in ['create', 'update', 'add-link-file', 'annotate-dataset',
                        'generate-file-templates', 'apply-file-annotations', 'set-version']:
        config.validate()

    # Route to appropriate handler
    if args.command == 'create':
        if args.from_annotations:
            handle_create_from_annotations(args, config)
        else:
            handle_create_workflow(args, config)
    elif args.command == 'update':
        handle_update_workflow(args, config)
    elif args.command == 'annotate-dataset':
        handle_annotate_dataset(args, config)
    elif args.command == 'generate-template':
        handle_generate_template(args, config)
    elif args.command == 'generate-file-templates':
        handle_generate_file_templates(args, config)
    elif args.command == 'apply-file-annotations':
        handle_apply_file_annotations(args, config)
    elif args.command == 'add-link-file':
        handle_add_link_file(args, config)
    elif args.command == 'generate-mapping':
        handle_generate_mapping(args, config)
    elif args.command == 'set-version':
        handle_set_version(args, config)
    elif args.command == 'delete-versions':
        handle_delete_versions_workflow(args, config)


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
