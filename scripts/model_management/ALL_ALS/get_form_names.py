import csv
import os
import sys
import json
import re

def get_descriptive_form_name(file_path):
    """
    Tries to extract the descriptive form name from the 'Form Name' or 'Form.Name'
    column in a CSV file.
    """
    try:
        with open(file_path, 'r') as f:
            reader = csv.reader(f)
            header = next(reader)
            header = [h.strip().replace('"', '') for h in header]

            form_name_index = -1
            possible_form_name_columns = ['Form Name', 'Form.Name']
            
            for col_name in possible_form_name_columns:
                if col_name in header:
                    form_name_index = header.index(col_name)
                    break
            
            if form_name_index != -1:
                # Find the first non-empty row and get the form name
                for row in reader:
                    if any(row) and len(row) > form_name_index:
                        return row[form_name_index]
                return "FILE IS EMPTY, no form name" # No data rows with content
            else:
                return None
    except (IOError, StopIteration):
        # This will catch empty files (StopIteration on next(reader))
        return "FILE IS EMPTY, no form name"
    except Exception:
        return None


def main(root_directory, output_file):
    """
    Generates a JSON file mapping short form names to descriptive form names.
    """
    form_name_mappings = {}
    
    all_files = []
    if not os.path.isdir(root_directory):
        print(f"Error: Directory not found - {root_directory}", file=sys.stderr)
        return

    for dirpath, _, filenames in os.walk(root_directory):
        for filename in filenames:
            if filename.endswith(".csv"):
                all_files.append(os.path.join(dirpath, filename))

    for file_path in all_files:
        filename = os.path.basename(file_path)
        # Updated regex to handle form names that might have underscores
        match = re.search(r'v_ALLALS_(?:PR|AS)_([A-Z0-9_]+)\.csv', filename)
        if match:
            short_form_name = match.group(1)
            descriptive_name = get_descriptive_form_name(file_path)
            
            if descriptive_name and descriptive_name.strip():
                form_name_mappings[short_form_name] = descriptive_name.strip()
            elif descriptive_name is None:
                 print(f"Warning: Could not find a 'Form Name' column in {filename}", file=sys.stderr)
            # If descriptive_name is the empty file message, it will be added.

    with open(output_file, 'w') as f:
        json.dump(form_name_mappings, f, indent=4, sort_keys=True)
    
    print(f"Successfully generated {output_file} with {len(form_name_mappings)} entries.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python get_form_names.py <root_directory>")
        sys.exit(1)
    
    root_directory = sys.argv[1]
    output_file = os.path.join("mapping", "ALL_ALS", "form_name_mappings.json")

    # Ensure the mapping directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    main(root_directory, output_file)
