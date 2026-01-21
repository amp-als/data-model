#!/usr/bin/env python
# coding: utf-8

# # Standard Operating Procedure for ALL-ALS Data Updates

# ## Step 1: Generate View Name to Class Name Mapping
# 
# This first step is to analyze the raw CSV files from the v2 data release to extract the 'Form Name' from each file. This 'Form Name' will be used to map to the class name in the data model.

# In[1]:


import os
import csv
import json

def get_form_names_from_datasets(base_dir):
    datasets = ["ASSESS", "PREVENT"]
    form_name_mapping = {}

    for dataset in datasets:
        dataset_files_path = os.path.join(base_dir, dataset, 'files')
        if not os.path.isdir(dataset_files_path):
            print(f"Directory not found: {dataset_files_path}")
            continue

        for filename in os.listdir(dataset_files_path):
            if filename.endswith(".csv"):
                file_path = os.path.join(dataset_files_path, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as csvfile:
                        reader = csv.reader(csvfile)
                        header = next(reader)
                        if "Form Name" in header:
                            form_name_index = header.index("Form Name")
                            try:
                                first_row = next(reader)
                                form_name = first_row[form_name_index]
                                # Clean up the filename to use as a key
                                clean_filename = os.path.splitext(filename)[0].replace('v_ALLALS_AS_', '').replace('v_ALLALS_PV_', '').replace('v_ALLALS_PR_', '').replace('-', '_')
                                form_name_mapping[clean_filename] = form_name
                            except StopIteration:
                                print(f"File is empty (after header): {filename}")
                        else:
                            print(f"'Form Name' column not found in {filename}")
                except Exception as e:
                    print(f"Error processing file {filename}: {e}")

    return form_name_mapping

if __name__ == "__main__":
    # The base directory where the ASSESS and PREVENT folders are located.
    base_directory = "/home/ramayyala/github/data-model/data/ALL_ALS/v2-OCT"
    mappings = get_form_names_from_datasets(base_directory)

    # Save the mappings to a file in the root of the project
    output_file_path = "/home/ramayyala/github/data-model/form_name_mappings.json"
    with open(output_file_path, 'w') as f:
        json.dump(mappings, f, indent=4)

    print(f"Mappings saved to {output_file_path}")

    # Print the mappings to the console as well
    for key, value in mappings.items():
        print(f"{key}: {value}")

