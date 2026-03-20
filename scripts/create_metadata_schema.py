#!/usr/bin/env python3
"""
Create Metadata Schema Generator

This script reads a metadata CSV file and generates a metadata schema template
by inferring data types and extracting unique values for potential enumerations.

Usage:
    python scripts/create_metadata_schema.py input_metadata.csv output_schema.json [options]

Options:
    --schema-name NAME        Name for the schema (default: derived from filename)
    --schema-type TYPE        Type: clinical, omics, or study (default: clinical)
    --version VERSION         Schema version (default: 1.0)
    --description DESC        Schema description
    --enum-threshold N        Max unique values to treat as enum (default: 20)
    --sample-size N           Number of rows to analyze (default: all)
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Set
from collections import Counter
import re


def infer_data_type(values: List[str], unique_count: int, enum_threshold: int) -> str:
    """
    Infer the data type from a list of values.

    Args:
        values: List of string values (excluding missing values)
        unique_count: Number of unique values
        enum_threshold: Max unique values to consider as enum

    Returns:
        Data type: string, integer, float, date, boolean, or enum
    """
    if not values:
        return "string"

    # Check for boolean
    unique_values = set(v.lower() for v in values)
    if unique_values <= {"true", "false", "yes", "no", "1", "0", "t", "f", "y", "n"}:
        return "boolean"

    # Check for date (YYYY-MM-DD format)
    date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    if all(date_pattern.match(v) for v in values[:100]):  # Check first 100
        return "date"

    # Check for integer
    try:
        int_values = [int(v) for v in values[:100]]
        # All parsed as int, check if they're actually integers
        if all(str(v) == str(int(v)) for v in values[:100]):
            return "integer"
    except (ValueError, TypeError):
        pass

    # Check for float
    try:
        float_values = [float(v) for v in values[:100]]
        return "float"
    except (ValueError, TypeError):
        pass

    # Check for enum based on unique value count
    if unique_count <= enum_threshold:
        return "enum"

    return "string"


def extract_valid_values(values: List[str], max_values: int = 50) -> List[Dict[str, str]]:
    """
    Extract unique values and their frequencies for enumerated fields.

    Args:
        values: List of values
        max_values: Maximum number of values to include

    Returns:
        List of dicts with 'value' and 'description' keys
    """
    # Count frequencies
    counter = Counter(values)

    # Get most common values
    valid_values = []
    for value, count in counter.most_common(max_values):
        valid_values.append({
            "value": value,
            "description": f"TODO: Add description for '{value}' (appears {count} times)"
        })

    return valid_values


def get_example_values(values: List[str], data_type: str, n: int = 5) -> List[str]:
    """
    Get example values for a field.

    Args:
        values: List of values
        data_type: Data type of the field
        n: Number of examples to return

    Returns:
        List of example values
    """
    if not values:
        return []

    # For enums, show the most common values
    if data_type == "enum":
        counter = Counter(values)
        return [str(v) for v, _ in counter.most_common(n)]

    # For numeric types, show a range
    if data_type in ["integer", "float"]:
        try:
            numeric_values = sorted(set(float(v) for v in values))
            # Sample evenly across the range
            step = max(1, len(numeric_values) // n)
            examples = numeric_values[::step][:n]
            return [str(int(v)) if data_type == "integer" else str(v) for v in examples]
        except (ValueError, TypeError):
            pass

    # For other types, show unique examples
    unique_values = list(dict.fromkeys(values))  # Preserve order
    return [str(v) for v in unique_values[:n]]


def analyze_column(column_name: str, values: List[str], enum_threshold: int) -> Dict[str, Any]:
    """
    Analyze a single column and create attribute definition.

    Args:
        column_name: Name of the column
        values: All values in the column (including missing)
        enum_threshold: Threshold for treating as enum

    Returns:
        Attribute definition dict
    """
    # Filter out missing values for analysis
    missing_indicators = {"", "NA", "N/A", "NULL", "None", "nan", "-", "NaN"}
    non_missing = [v for v in values if v not in missing_indicators]

    # Calculate basic stats
    total_count = len(values)
    non_missing_count = len(non_missing)
    unique_count = len(set(non_missing))
    missing_rate = (total_count - non_missing_count) / total_count if total_count > 0 else 0

    # Infer data type
    data_type = infer_data_type(non_missing, unique_count, enum_threshold)

    # Build attribute definition
    attribute = {
        "name": column_name,
        "description": f"TODO: Add description for {column_name}",
        "dataType": data_type,
        "required": missing_rate < 0.1  # Less than 10% missing = required
    }

    # Add valid values for enums
    if data_type == "enum":
        attribute["validValues"] = extract_valid_values(non_missing)

    # Add examples
    attribute["examples"] = get_example_values(non_missing, data_type)

    # Add validation rules hint for numeric types
    if data_type in ["integer", "float"] and non_missing:
        try:
            numeric_values = [float(v) for v in non_missing]
            min_val = min(numeric_values)
            max_val = max(numeric_values)
            if data_type == "integer":
                attribute["validationRules"] = f"TODO: Verify range ({int(min_val)} to {int(max_val)} observed)"
            else:
                attribute["validationRules"] = f"TODO: Verify range ({min_val:.2f} to {max_val:.2f} observed)"
        except (ValueError, TypeError):
            pass

    return attribute


def create_schema_from_csv(
    csv_path: Path,
    schema_name: str = None,
    schema_type: str = "clinical",
    version: str = "1.0",
    description: str = None,
    enum_threshold: int = 20,
    sample_size: int = None
) -> Dict[str, Any]:
    """
    Create a metadata schema from a CSV file.

    Args:
        csv_path: Path to input CSV file
        schema_name: Name for the schema
        schema_type: Type of schema (clinical, omics, study)
        version: Schema version
        description: Schema description
        enum_threshold: Max unique values to treat as enum
        sample_size: Number of rows to analyze (None = all)

    Returns:
        Schema dictionary
    """
    # Read CSV file
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        # Read all rows or sample
        rows = []
        for i, row in enumerate(reader):
            if sample_size and i >= sample_size:
                break
            rows.append(row)

    if not rows:
        raise ValueError(f"No data found in {csv_path}")

    # Get column names
    column_names = list(rows[0].keys())

    # Organize values by column
    columns_data = {col: [row[col] for row in rows] for col in column_names}

    # Analyze each column
    attributes = []
    for col_name in column_names:
        attribute = analyze_column(col_name, columns_data[col_name], enum_threshold)
        attributes.append(attribute)

    # Create schema
    if not schema_name:
        schema_name = csv_path.stem.replace('_', ' ').title().replace(' ', '')

    if not description:
        description = f"TODO: Add description for {schema_name} schema"

    schema = {
        "schemaName": schema_name,
        "schemaType": schema_type,
        "version": version,
        "description": description,
        "attributes": attributes
    }

    return schema


def main():
    parser = argparse.ArgumentParser(
        description="Generate metadata schema template from CSV file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python scripts/create_metadata_schema.py input.csv output.json

  # With custom options
  python scripts/create_metadata_schema.py input.csv output.json \\
    --schema-name "ClinicalData" \\
    --schema-type clinical \\
    --description "Clinical assessment data" \\
    --enum-threshold 15

  # Analyze only first 1000 rows
  python scripts/create_metadata_schema.py large_file.csv output.json --sample-size 1000
        """
    )

    parser.add_argument("input_csv", type=Path, help="Input CSV metadata file")
    parser.add_argument("output_json", type=Path, help="Output JSON schema file")
    parser.add_argument("--schema-name", help="Name for the schema")
    parser.add_argument(
        "--schema-type",
        choices=["clinical", "omics", "study"],
        default="clinical",
        help="Type of schema (default: clinical)"
    )
    parser.add_argument("--version", default="1.0", help="Schema version (default: 1.0)")
    parser.add_argument("--description", help="Schema description")
    parser.add_argument(
        "--enum-threshold",
        type=int,
        default=20,
        help="Max unique values to treat as enum (default: 20)"
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        help="Number of rows to analyze (default: all)"
    )

    args = parser.parse_args()

    # Validate input file
    if not args.input_csv.exists():
        print(f"Error: Input file not found: {args.input_csv}", file=sys.stderr)
        sys.exit(1)

    # Create schema
    print(f"Analyzing {args.input_csv}...")
    try:
        schema = create_schema_from_csv(
            args.input_csv,
            schema_name=args.schema_name,
            schema_type=args.schema_type,
            version=args.version,
            description=args.description,
            enum_threshold=args.enum_threshold,
            sample_size=args.sample_size
        )
    except Exception as e:
        print(f"Error creating schema: {e}", file=sys.stderr)
        sys.exit(1)

    # Write output
    print(f"Writing schema to {args.output_json}...")
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_json, 'w', encoding='utf-8') as f:
        json.dump(schema, f, indent=2)

    # Print summary
    print(f"\nSchema created successfully!")
    print(f"  Schema name: {schema['schemaName']}")
    print(f"  Schema type: {schema['schemaType']}")
    print(f"  Attributes: {len(schema['attributes'])}")
    print(f"\nNext steps:")
    print(f"  1. Review the generated schema at {args.output_json}")
    print(f"  2. Update TODO items with proper descriptions")
    print(f"  3. Verify data types and validation rules")
    print(f"  4. Review enum values and add meaningful descriptions")


if __name__ == "__main__":
    main()
