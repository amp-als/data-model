import json
import argparse
import pandas as pd
from pathlib import Path
from jsonata import jsonata
from jsonschema import validate, ValidationError

def load_mapping(mapping_file):
    """Load the JSONata mapping expression from a file"""
    with open(mapping_file, 'r') as f:
        return f.read()
    
def load_schema(schema_file):
    """Load the JSON Schema from a file"""
    with open(schema_file, 'r') as f:
        return json.load(f)

def load_csv_files(data_directory):
    """Load all CSV files from the PREVENT data directory"""
    csv_files = {}
    data_path = Path(data_directory)
    
    # Load all CSV files in the directory
    for csv_file in data_path.glob("*.csv"):
        df = pd.read_csv(csv_file)
        # Use filename (without extension) as key
        key = csv_file.stem
        csv_files[key] = df
        print(f"Loaded {len(df)} rows from {csv_file.name}")
    
    return csv_files

def merge_csv_data(csv_files):
    """Merge CSV files on common keys (SubjectUID, Visit info, etc.)"""
    # Start with the largest file or subjects file as base
    base_df = None
    base_key = None
    
    # Find subjects file or largest file as base
    for key, df in csv_files.items():
        if 'subject' in key.lower():
            base_df = df
            base_key = key
            break
    
    if base_df is None:
        # Use largest file as base
        base_key = max(csv_files.keys(), key=lambda k: len(csv_files[k]))
        base_df = csv_files[base_key]
    
    print(f"Using {base_key} as base with {len(base_df)} rows")
    
    # Merge other files
    merged_df = base_df.copy()
    
    for key, df in csv_files.items():
        if key == base_key:
            continue
            
        # Determine merge keys based on available columns
        merge_keys = []
        if 'SubjectUID' in df.columns and 'SubjectUID' in merged_df.columns:
            merge_keys.append('SubjectUID')
        if 'Visit' in df.columns and 'Visit' in merged_df.columns:
            merge_keys.append('Visit')
        if 'Date' in df.columns and 'Date' in merged_df.columns:
            merge_keys.append('Date')
            
        if merge_keys:
            print(f"Merging {key} on {merge_keys}")
            merged_df = merged_df.merge(df, on=merge_keys, how='outer', suffixes=('', f'_{key}'))
        else:
            print(f"Warning: Could not merge {key} - no common keys found")
    
    print(f"Final merged data has {len(merged_df)} rows and {len(merged_df.columns)} columns")
    return merged_df

def dataframe_to_json_records(df):
    """Convert DataFrame to JSON records, handling NaN values"""
    # Replace NaN with None for JSON compatibility
    df_clean = df.where(pd.notnull(df), None)
    return df_clean.to_dict('records')

def validate_item(item, schema):
    """Validate an item against a JSON Schema"""
    try:
        validate(instance=item, schema=schema)
        return True, None
    except ValidationError as e:
        return False, str(e)

def transform_with_jsonata(source_data, mapping_expr, schema=None):
    """Transform source data using a JSONata expression and validate against schema"""
    # Compile the JSONata expression once
    expr = jsonata.Jsonata(mapping_expr)
    
    # Apply the JSONata transformation
    try:
        result = expr.evaluate(source_data)
    except Exception as e:
        print(f"JSONata transformation error: {e}")
        raise
    
    # Validate against schema if provided
    validation_errors = []
    if schema:
        # Validate each entity type if result is structured
        if isinstance(result, dict):
            for entity_type, entities in result.items():
                if isinstance(entities, list):
                    for i, entity in enumerate(entities):
                        is_valid, error = validate_item(entity, schema)
                        if not is_valid:
                            validation_errors.append({
                                "entity_type": entity_type,
                                "entity_index": i,
                                "error": error,
                                "entity": entity
                            })
    
    return result, validation_errors

def main():
    parser = argparse.ArgumentParser(description='Transform ALL ALS PREVENT CSV data using JSONata mapping')
    parser.add_argument('data_directory', help='Path to directory containing PREVENT CSV files')
    parser.add_argument('mapping_file', help='Path to JSONata mapping file (default: prevent.jsonata)', 
                        default='mapping/prevent.jsonata', nargs='?')
    parser.add_argument('-s', '--schema', help='Path to JSON Schema file for validation')
    parser.add_argument('-o', '--output', help='Path to output JSON file (optional)')
    parser.add_argument('--strict', action='store_true', help='Fail if any validation errors occur')
    parser.add_argument('--log-errors', help='Path to error log file')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    args = parser.parse_args()
    
    try:
        # Load CSV files
        print("Loading CSV files...")
        csv_files = load_csv_files(args.data_directory)
        
        if not csv_files:
            print("Error: No CSV files found in the specified directory")
            return 1
        
        # Merge CSV data
        print("Merging CSV data...")
        merged_df = merge_csv_data(csv_files)
        
        # Convert to JSON records
        print("Converting to JSON records...")
        json_data = dataframe_to_json_records(merged_df)
        
        if args.debug:
            print(f"Sample record keys: {list(json_data[0].keys()) if json_data else 'No data'}")
        
        # Load mapping
        print("Loading JSONata mapping...")
        mapping_expr = load_mapping(args.mapping_file)
        
        # Load schema if provided
        schema = None
        if args.schema:
            print("Loading validation schema...")
            schema = load_schema(args.schema)
        
        # Transform data
        print("Applying JSONata transformation...")
        transformed_data, validation_errors = transform_with_jsonata(json_data, mapping_expr, schema)
        
        # Handle validation errors
        if validation_errors:
            print(f"Found {len(validation_errors)} validation errors.")
            
            # Write errors to log file if specified
            if args.log_errors:
                with open(args.log_errors, 'w') as f:
                    json.dump(validation_errors, f, indent=2)
                print(f"Validation errors written to {args.log_errors}")
            
            # Exit with error if in strict mode
            if args.strict:
                print("Exiting due to validation errors in strict mode.")
                return 1

        # Count entities if structured output
        if isinstance(transformed_data, dict):
            for entity_type, entities in transformed_data.items():
                if isinstance(entities, list):
                    print(f"Generated {len(entities)} {entity_type}")

        # Write or print the output
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(transformed_data, f, indent=2)
            print(f"Transformed data written to {args.output}")
        else:
            print(json.dumps(transformed_data, indent=2))
        
        print("Transformation completed successfully!")
        return 0
        
    except Exception as e:
        print(f"Error during transformation: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())