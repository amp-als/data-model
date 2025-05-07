import json
import argparse
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

def validate_item(item, schema):
    """Validate an item against a JSON Schema"""
    try:
        validate(instance=item, schema=schema)
        return True, None
    except ValidationError as e:
        return False, str(e)

def transform_with_jsonata(source_items, mapping_expr, schema=None):
    """Transform a list of items using a JSONata expression and validate against schema"""
    # Compile the JSONata expression once
    expr = jsonata.Jsonata(mapping_expr)
    
    # Apply the transformation to each item
    transformed_items = []
    validation_errors = []
    
    for i, item in enumerate(source_items):
        # Apply the JSONata transformation
        result = expr.evaluate(item)
        
        # Validate against schema if provided
        if schema:
            is_valid, error = validate_item(result, schema)
            if not is_valid:
                validation_errors.append({
                    "item_index": i,
                    "error": error,
                    "transformed_item": result
                })
                continue  # Skip invalid items
        
        transformed_items.append(result)
    
    return transformed_items, validation_errors

def main():
    parser = argparse.ArgumentParser(description='Transform JSON using JSONata mapping')
    parser.add_argument('input_file', help='Path to input JSON file')
    parser.add_argument('mapping_file', help='Path to JSONata mapping file')
    parser.add_argument('-s', '--schema', help='Path to JSON Schema file for validation')
    parser.add_argument('-o', '--output', help='Path to output JSON file (optional)')
    parser.add_argument('--strict', action='store_true', help='Fail if any validation errors occur')
    parser.add_argument('--log-errors', help='Path to error log file')
    args = parser.parse_args()
    
    with open(args.input_file, 'r') as f:
        data = json.load(f)
    
    # Files
    mapping_expr = load_mapping(args.mapping_file)
    schema = None
    if args.schema:
        schema = load_schema(args.schema)
    
    transformed_items, validation_errors = transform_with_jsonata(data['items'], mapping_expr, schema)
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

    # Write or print the output
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(transformed_items, f, indent=2)
        print(f"Transformed data written to {args.output}")
        print(f"Successfully transformed {len(transformed_items)} items.")
    else:
        print(json.dumps(transformed_items, indent=2))
    
    return 0

if __name__ == "__main__":
    main()
