
import json
import os
import pandas as pd
import yaml
from pathlib import Path

def get_unique_subject_count(file_path, subject_column):
    """Counts the number of unique subjects in a CSV file."""
    if not os.path.exists(file_path):
        return 0
    try:
        df = pd.read_csv(file_path)
        if subject_column in df.columns:
            return df[subject_column].nunique()
    except Exception:
        return 0
    return 0

def find_subject_column(file_path):
    """Finds the subject ID column in a CSV file."""
    if not os.path.exists(file_path):
        return None
    try:
        df = pd.read_csv(file_path, nrows=0)
        for col in df.columns:
            if 'subj' in col.lower() or 'uid' in col.lower():
                return col
    except Exception:
        return None
    return 'SubjectUID' # Fallback

def get_description_from_schema(schemas, assessment_type):
    """Gets the description for an assessment type from the schemas."""
    for schema_data in schemas.values():
        if 'classes' in schema_data:
            for class_name, class_def in schema_data['classes'].items():
                if class_name == assessment_type:
                    return class_def.get('description', '')
    # Check in enums too
    for schema_data in schemas.values():
        if 'enums' in schema_data:
            for enum_name, enum_def in schema_data['enums'].items():
                if enum_name == "AssessmentTypeEnum":
                    if assessment_type in enum_def.get('permissible_values', {}):
                        return enum_def['permissible_values'][assessment_type].get('description', '')
    return ''

def main():
    annotations_file = 'annotations/all_als/assess_file_annotations.json'
    data_dir = 'data/ALL_ALS/v3-DEC/ASSESS/files'
    schema_dir = 'modules'

    # Load annotations
    with open(annotations_file, 'r') as f:
        annotations = json.load(f)

    # Load all schemas
    schemas = {}
    for p in Path(schema_dir).rglob('*.yaml'):
        with open(p, 'r') as f:
            schemas[p.name] = yaml.safe_load(f)

    # Process each annotation
    for syn_id, file_info in annotations.items():
        for file_key, ann in file_info.items():
            
            # Fill title if empty
            if not ann.get('title'):
                ann['title'] = file_key

            # Fill alternateName if empty and viewName exists
            if not ann.get('alternateName') and ann.get('viewName') and ann.get('viewName')[0]:
                ann['alternateName'] = ann['viewName'][0]

            # Fill description if empty and assessmentType exists
            if not ann.get('description') and ann.get('assessmentType') and ann.get('assessmentType')[0]:
                ann['description'] = get_description_from_schema(schemas, ann['assessmentType'][0])
            
            # Fill keywords if empty
            if not ann.get('keywords') or ann['keywords'] == ['']:
                keywords = []
                if ann.get('dataType'):
                    keywords.extend(ann['dataType'])
                if ann.get('clinicalDomain'):
                    keywords.extend(ann['clinicalDomain'])
                if ann.get('assessmentType'):
                    keywords.extend(ann['assessmentType'])
                if ann.get('keyMeasures'):
                    keywords.extend(ann['keyMeasures'])
                ann['keywords'] = list(set(keywords)) if keywords else [""]
            
            # Fill collection if empty
            if not ann.get('collection') or ann['collection'] == ['']:
                if ann.get('dataSourcePrefix'):
                    ann['collection'] = ann['dataSourcePrefix']
            
            # Fill license if empty
            if not ann.get('license'):
                ann['license'] = 'UNKNOWN'

            # Fill source if empty
            if not ann.get('source'):
                if ann.get('dataSourcePrefix'):
                    ann['source'] = ann['dataSourcePrefix'][0]
            
            # Infer visitType
            if not ann.get('visitType'):
                if ann.get('studyPhase') and 'screening' in ann.get('studyPhase'):
                    ann['visitType'] = 'Screening'
                elif ann.get('studyPhase') and 'longitudinal' in ann.get('studyPhase'):
                    ann['visitType'] = 'Follow-up'

            # Infer administrationMode
            if not ann.get('administrationMode'):
                 if ann.get('visitType') == 'Screening' or (ann.get('assessmentType') and 'ECAS' not in ann.get('assessmentType')[0]):
                    ann['administrationMode'] = 'In_Person'

            view_name = ann.get('viewName')[0] if ann.get('viewName') else None
            if view_name:
                data_file_path = os.path.join(data_dir, f"{view_name}.csv")
                
                # Fill subjectIdColumn if empty
                if not ann.get('subjectIdColumn'):
                    subject_id_column = find_subject_column(data_file_path)
                    if subject_id_column:
                        ann['subjectIdColumn'] = subject_id_column
                else:
                    subject_id_column = ann['subjectIdColumn']
                
                # Fill individualCount if empty and subject_id_column is found
                if (not ann.get('individualCount') or ann['individualCount'] == "") and subject_id_column:
                    count = get_unique_subject_count(data_file_path, subject_id_column)
                    if count > 0:
                        ann['individualCount'] = count

    
    # Write updated annotations
    with open(annotations_file, 'w') as f:
        json.dump(annotations, f, indent=2)

    print("Annotations updated successfully.")

if __name__ == '__main__':
    main()
