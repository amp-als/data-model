# Metadata Schema Guide

## Overview

This guide explains how to create and use metadata schemas to document clinical and omics data attributes. Metadata schemas provide a standardized way to describe:

- What each column/attribute represents
- What data type it uses
- What values are allowed (for enumerations)
- Example values to help users understand the data
- **NEW:** Dataset-level citation metadata for discovery and reuse (NIH CADR compliance)

### Two Uses of Metadata Schemas

This system supports two complementary use cases:

1. **Attribute Documentation** - Document columns/fields within data files
   - Example: "age_in_years is an integer between 18-120"
   - Used by data collectors and analysts

2. **Dataset Citation** - Document the dataset itself for discovery, reuse, and citation
   - Example: "This dataset was created by John Smith, published 2023, DOI: 10.xxxx"
   - Required for NIH CADR compliance
   - Enables proper attribution and findability

You can use one schema to handle both purposes! See `/docs/nih-cadr-compliance.md` for full details on NIH requirements.

## Schema Structure

A metadata schema is a JSON document with the following structure:

```json
{
  "schemaName": "string",
  "schemaType": "clinical | omics | study | dataset",
  "version": "string",
  "description": "string",

  "identifier": "optional DOI or persistent ID",
  "title": "optional dataset title",
  "creators": ["optional authors"],
  "license": "optional license",

  "attributes": [...]
}
```

### Schema-Level Fields

#### Core Fields (Always Required)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schemaName` | string | Yes | Name of this schema (e.g., "ClinicalAssessmentMetadata") |
| `schemaType` | enum | Yes | Type: `clinical`, `omics`, `study`, or `dataset` |
| `version` | string | Yes | Version number (e.g., "1.0", "2.1") |
| `description` | string | No | Overall description of what this schema covers |
| `attributes` | array | Yes | List of attribute definitions (see below) |

#### Citation Metadata Fields (Optional, for NIH CADR Compliance)

These fields enable dataset discovery, reuse, and citation. Include them when documenting a complete dataset:

| Field | Type | Description |
|-------|------|-------------|
| `identifier` | string | Persistent identifier (DOI, ARK, Handle) |
| `identifierType` | enum | Type of identifier (DOI, ARK, Handle, URL) |
| `title` | string | Dataset title |
| `creators` | array | Authors/creators (with ORCID if available) |
| `contributors` | array | Additional contributors with roles |
| `publisher` | string | Publishing institution |
| `publicationYear` | integer | Year made publicly available |
| `subjects` | array | Keywords/topics (use controlled vocabularies) |
| `license` | string | Usage license (CC-BY-4.0, etc.) |
| `licenseURL` | string | URL to full license text |
| `accessRights` | enum | Access restrictions (Open, Restricted, Controlled) |
| `fundingReferences` | array | Funding information |
| `relatedPublications` | array | Related publication DOIs |
| `contactEmail` | string | Contact for questions |
| `citationRecommendation` | string | How to cite this dataset |
| `conformsTo` | array | Standards this schema aligns with |

See `/docs/nih-cadr-compliance.md` for full details on citation metadata.

### Attribute Fields

Each attribute in the `attributes` array describes a single column/field:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Column/attribute name (e.g., "age_in_years") |
| `description` | string | Yes | What this attribute represents |
| `dataType` | enum | Yes | Data type: `string`, `integer`, `float`, `date`, `datetime`, `boolean`, or `enum` |
| `required` | boolean | No | Whether this attribute must be present in the data |
| `validValues` | array | No | Allowed values for `enum` type (see below) |
| `validationRules` | string | No | Optional validation constraints |
| `examples` | array | No | Example values to help users |

### Valid Values (for Enumerations)

For attributes with `dataType: "enum"`, the `validValues` field contains allowed values:

```json
{
  "name": "clinical_group",
  "dataType": "enum",
  "validValues": [
    {
      "value": "ALS",
      "description": "Amyotrophic Lateral Sclerosis patient"
    },
    {
      "value": "Non-Neurological Control",
      "description": "Healthy control participant"
    }
  ]
}
```

## Data Types

### string
Text string value of any length.

**Example:**
```json
{
  "name": "subject_id",
  "description": "Unique identifier for the subject",
  "dataType": "string",
  "required": true,
  "examples": ["SUBJECT_001", "NEUAJ018HDE"]
}
```

### integer
Whole number (positive or negative).

**Example:**
```json
{
  "name": "age_in_years",
  "description": "Age of participant in years",
  "dataType": "integer",
  "required": true,
  "validationRules": "Must be between 18 and 120",
  "examples": ["45", "52", "63", "71"]
}
```

### float
Decimal number.

**Example:**
```json
{
  "name": "sample_volume",
  "description": "Volume of sample in mL",
  "dataType": "float",
  "required": false,
  "validationRules": "Must be positive",
  "examples": ["5.0", "10.5", "2.5"]
}
```

### date
Date in YYYY-MM-DD format.

**Example:**
```json
{
  "name": "collection_date",
  "description": "Date when sample was collected",
  "dataType": "date",
  "required": true,
  "validationRules": "Format: YYYY-MM-DD",
  "examples": ["2023-01-15", "2023-06-22"]
}
```

### datetime
Date and time in ISO 8601 format.

**Example:**
```json
{
  "name": "sequencing_start_time",
  "description": "When sequencing run started",
  "dataType": "datetime",
  "required": false,
  "validationRules": "Format: ISO 8601 (YYYY-MM-DDTHH:MM:SSZ)",
  "examples": ["2023-01-15T09:30:00Z", "2023-06-22T14:15:30Z"]
}
```

### boolean
True/false value.

**Example:**
```json
{
  "name": "protocol_deviation",
  "description": "Whether any protocol deviation occurred",
  "dataType": "boolean",
  "required": false,
  "examples": ["false", "true"]
}
```

### enum
Value from a fixed set of allowed options. Must include `validValues` array.

**Example:**
```json
{
  "name": "sex_reported",
  "description": "Self-reported biological sex",
  "dataType": "enum",
  "required": true,
  "validValues": [
    {
      "value": "Male",
      "description": "Male sex"
    },
    {
      "value": "Female",
      "description": "Female sex"
    }
  ],
  "examples": ["Male", "Female"]
}
```

## Validation Rules

The `validationRules` field provides human-readable constraints for an attribute. Common patterns:

### Numeric Ranges
```json
"validationRules": "Must be between 18 and 120"
"validationRules": "Must be positive"
"validationRules": "Score range 0-20"
```

### Date Formats
```json
"validationRules": "Format: YYYY-MM-DD"
"validationRules": "Format: ISO 8601 (YYYY-MM-DDTHH:MM:SSZ)"
```

### Special Codes
```json
"validationRules": "Must be between 1900 and current year, or special codes: -5555 (N/A), -8888 (Unknown), -9999 (Not collected)"
```

### String Formats
```json
"validationRules": "Format: HH:MM (24-hour format)"
"validationRules": "Must be unique across the dataset"
```

## Creating a Schema Manually

### Step 1: Start with the Template

Create a new JSON file with the basic structure:

```json
{
  "schemaName": "YourSchemaName",
  "schemaType": "clinical",
  "version": "1.0",
  "description": "Description of what this schema covers",
  "attributes": []
}
```

### Step 2: Add Attributes

For each column in your metadata file, add an attribute definition:

1. **Identify the column name** - use the exact name from your data
2. **Write a clear description** - explain what this column represents
3. **Choose the appropriate data type** - string, integer, float, date, boolean, or enum
4. **Mark as required or optional** - based on whether the field must always be present
5. **Add valid values** (for enums) - list all allowed values with descriptions
6. **Add validation rules** (optional) - document any constraints
7. **Provide examples** - show 3-5 example values

### Step 3: Review and Validate

1. Check that all column names match your data exactly
2. Verify data types are appropriate for the values
3. Ensure enum values cover all possibilities in your data
4. Confirm descriptions are clear and complete
5. Validate the JSON syntax

## Auto-Generating Schemas

Use the `create_metadata_schema.py` script to automatically generate a schema template from an existing CSV file:

```bash
python scripts/create_metadata_schema.py input_metadata.csv output_schema.json
```

### Basic Usage

```bash
# Generate schema from CSV
python scripts/create_metadata_schema.py clinical_data.csv clinical_schema.json

# With custom options
python scripts/create_metadata_schema.py clinical_data.csv clinical_schema.json \
  --schema-name "ClinicalAssessment" \
  --schema-type clinical \
  --description "Clinical assessment metadata" \
  --enum-threshold 15
```

### Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--schema-name NAME` | Name for the schema | Derived from filename |
| `--schema-type TYPE` | Schema type: clinical, omics, study | clinical |
| `--version VERSION` | Schema version | 1.0 |
| `--description DESC` | Schema description | Auto-generated |
| `--enum-threshold N` | Max unique values to treat as enum | 20 |
| `--sample-size N` | Number of rows to analyze | All rows |

### What the Script Does

The auto-generation script:

1. **Reads your CSV file** and analyzes the data
2. **Infers data types** from the values:
   - Detects integers, floats, dates, booleans
   - Identifies enumerations (fields with few unique values)
   - Defaults to string for everything else
3. **Extracts unique values** for enum fields
4. **Generates example values** for each attribute
5. **Creates validation rule hints** for numeric ranges
6. **Identifies required fields** (< 10% missing values)

### Post-Generation Steps

After generating a schema, you should:

1. **Review TODO items** - replace auto-generated placeholders
2. **Update descriptions** - add meaningful descriptions for each attribute
3. **Verify data types** - ensure inferred types are correct
4. **Review enum values** - add descriptions for each valid value
5. **Check validation rules** - verify numeric ranges and formats
6. **Update required flags** - adjust based on your data requirements

## Pre-Defined Schema Templates

The repository includes several pre-defined schema templates in `/templates/metadata-schemas/`:

### 1. Clinical Assessment Schema
**File:** `clinical_assessment_schema.json`

Covers clinical assessment metadata including:
- Visit information (visit_number)
- Diagnosis (als_diagnosis_revised_el_escorial, site_of_motor_onset)
- Demographics (age_in_years, sex_reported, race, ethnicity)
- Genetic information (reported_c9orf72_mutation)
- Assessment scores (als_cbs_score)

### 2. Omics Sample Metadata Schema
**File:** `omics_sample_schema.json`

Covers omics sample metadata including:
- Sample identifiers (sample_id, subject_id)
- Biospecimen information (biospecimen_type, collection_date)
- Assay details (assay_type, platform, library_layout)
- Processing level (raw, processed, analyzed)

### 3. Subject Demographics Schema
**File:** `subject_demographics_schema.json`

Covers subject demographic information:
- Identifiers and dates (subject_id, enrollment_date)
- Demographics (age_at_enrollment, sex_reported, race, ethnicity)
- Education and lifestyle (education_level, handedness)
- Medical history (family_history_als)

### 4. Biospecimen Collection Schema
**File:** `biospecimen_collection_schema.json`

Covers biospecimen collection and storage:
- Sample identification (sample_id, subject_id, visit_number)
- Collection details (biospecimen_type, anatomical_site, collection_date/time)
- Processing (fasting_status, collection_tube_type, processing_time)
- Storage (storage_temperature, freeze_thaw_cycles, sample_quality)

### 5. Study Visit Schema
**File:** `study_visit_schema.json`

Covers study visit management:
- Visit identification (subject_id, visit_number, visit_name)
- Scheduling (scheduled_date, actual_date, visit_window)
- Status (visit_status, protocol_deviation)
- Visit details (assessments_completed, site_id, duration)

### Using Templates

To use a template:

1. **Copy the template** to your working directory
2. **Customize for your needs**:
   - Update schema name and description
   - Add/remove attributes as needed
   - Modify valid values for enums
   - Adjust validation rules
3. **Save with a descriptive name**

## Examples

### Example 1: Simple Clinical Field

```json
{
  "name": "visit_number",
  "description": "Sequential visit number for the study",
  "dataType": "integer",
  "required": true,
  "examples": ["1", "2", "3", "4", "5"]
}
```

### Example 2: Enumerated Field

```json
{
  "name": "biospecimen_type",
  "description": "Type of biological specimen",
  "dataType": "enum",
  "required": true,
  "validValues": [
    {
      "value": "blood",
      "description": "Whole blood sample"
    },
    {
      "value": "plasma",
      "description": "Blood plasma"
    },
    {
      "value": "CSF",
      "description": "Cerebrospinal fluid"
    }
  ],
  "examples": ["blood", "plasma", "CSF"]
}
```

### Example 3: Numeric Field with Validation

```json
{
  "name": "age_in_years",
  "description": "Age of participant in years at time of assessment",
  "dataType": "integer",
  "required": true,
  "validationRules": "Must be between 18 and 120, or -9999 for missing data",
  "examples": ["45", "52", "63", "58", "71"]
}
```

### Example 4: Date Field

```json
{
  "name": "collection_date",
  "description": "Date when sample was collected",
  "dataType": "date",
  "required": true,
  "validationRules": "Format: YYYY-MM-DD",
  "examples": ["2023-01-15", "2023-06-22"]
}
```

### Example 5: Complete Schema with Citation Metadata

This example shows a full schema with both dataset-level citation metadata (for NIH CADR compliance) and attribute definitions:

```json
{
  "schemaName": "TargetALSClinicalData",
  "schemaType": "clinical",
  "version": "1.0",
  "description": "Clinical assessment data from the Target ALS Natural History Study",
  "conformsTo": [
    "https://schema.datacite.org/meta/kernel-4.4/",
    "http://purl.org/dc/terms/"
  ],

  "identifier": "10.7303/syn12345678",
  "identifierType": "DOI",
  "title": "Target ALS Natural History Study - Clinical Data",
  "creators": [
    "Smith, John (0000-0001-2345-6789)",
    "Doe, Jane (0000-0002-3456-7890)"
  ],
  "publisher": "Sage Bionetworks",
  "publicationYear": 2023,
  "subjects": [
    "Amyotrophic Lateral Sclerosis",
    "clinical assessment",
    "ALSFRS-R"
  ],
  "license": "CC-BY-NC-4.0",
  "accessRights": "Controlled",
  "fundingReferences": ["NIH/NINDS (U01NS107027)"],
  "contactEmail": "data@targetals.org",
  "citationRecommendation": "Smith, J., Doe, J. (2023). Target ALS Natural History Study - Clinical Data. Sage Bionetworks. https://doi.org/10.7303/syn12345678",

  "attributes": [
    {
      "name": "visit_number",
      "description": "Sequential visit number for the study",
      "dataType": "integer",
      "required": true,
      "examples": ["1", "2", "3"]
    },
    {
      "name": "clinical_group",
      "description": "Clinical group classification",
      "dataType": "enum",
      "required": true,
      "validValues": [
        {
          "value": "ALS",
          "description": "ALS patient"
        },
        {
          "value": "Control",
          "description": "Healthy control"
        }
      ],
      "examples": ["ALS", "Control"]
    }
  ]
}
```

See `/templates/metadata-schemas/dataset_with_citation_example.json` for the complete example.

## Best Practices

### Naming Conventions

- **Use snake_case** for attribute names (e.g., `age_in_years`, not `AgeInYears`)
- **Be descriptive** but concise (e.g., `als_cbs_score` rather than just `score`)
- **Use standard terminology** when available (e.g., `subject_id` rather than `participant_identifier`)

### Writing Descriptions

- **Start with what it is**, not how to use it
  - Good: "Age of participant in years at time of assessment"
  - Poor: "Enter the participant's age here"
- **Include units** when relevant (e.g., "in years", "in mL", "in minutes")
- **Mention key details** like timing or context
  - Example: "at time of enrollment" vs "at time of assessment"

### Choosing Data Types

- Use **enum** when:
  - There's a fixed set of allowed values
  - The list is relatively short (< 50 values)
  - Values are meaningful categories (not arbitrary IDs)
- Use **integer** vs **float**:
  - Integer: ages, counts, visit numbers
  - Float: measurements, concentrations, ratios
- Use **date** vs **datetime**:
  - Date: collection dates, enrollment dates
  - Datetime: timestamps, sequencing run times

### Enum Values

- **Cover all possibilities** that appear in your data
- **Write clear descriptions** for each value
  - Explain what the value means, not just repeat the value
  - Good: "Definite ALS - Meets criteria for definite ALS"
  - Poor: "Definite ALS - Definite ALS"
- **Include special codes** if used (e.g., "N/A", "Unknown", "PEN")

### Validation Rules

- **Be specific** about formats and ranges
- **Include special values** (e.g., -9999 for missing)
- **Use examples** when helpful:
  - "Format: YYYY-MM-DD"
  - "Format: HH:MM (24-hour format)"

### Required vs Optional

Mark a field as `required: true` when:
- The field must always have a value
- It's a key identifier or critical metadata
- Less than 10% of records are expected to be missing

Mark as `required: false` when:
- The field may legitimately be missing
- It's optional per protocol
- It applies only to certain subgroups

## Validation

### Manual Validation

Check your schema against this checklist:

- [ ] All required fields are present (schemaName, schemaType, version, attributes)
- [ ] All attributes have name, description, and dataType
- [ ] Enum types include validValues array
- [ ] Valid values have both value and description
- [ ] Examples are provided for each attribute
- [ ] No TODO placeholders remain
- [ ] JSON syntax is valid

### JSON Schema Validation

The LinkML schema generates a JSON Schema file at `/json-schemas/MetadataSchema.json`. You can use this to validate your metadata schemas programmatically:

```python
import json
import jsonschema

# Load the JSON Schema
with open('json-schemas/MetadataSchema.json') as f:
    json_schema = json.load(f)

# Load your metadata schema
with open('your_schema.json') as f:
    metadata_schema = json.load(f)

# Validate
try:
    jsonschema.validate(metadata_schema, json_schema)
    print("Schema is valid!")
except jsonschema.ValidationError as e:
    print(f"Validation error: {e.message}")
```

## Common Use Cases

### Use Case 1: Documenting Clinical Data

You have a CSV file with clinical assessment data and want to document what each column means:

1. **Run the auto-generator**:
   ```bash
   python scripts/create_metadata_schema.py clinical_data.csv clinical_schema.json \
     --schema-type clinical \
     --enum-threshold 15
   ```

2. **Review and update**:
   - Add descriptions for each column
   - Verify enum values make sense
   - Add descriptions for enum values
   - Check validation rules

3. **Save and share** the schema with your team

### Use Case 2: Standardizing Metadata Across Projects

You want to ensure consistent metadata structure across multiple studies:

1. **Start with a template** (e.g., `clinical_assessment_schema.json`)
2. **Customize for your project**:
   - Keep standard fields (age, sex, etc.)
   - Add project-specific fields
   - Adjust valid values as needed
3. **Use the same schema** across all studies
4. **Version the schema** when changes are needed

### Use Case 3: Validating Data Submissions

You want to check if submitted data matches your schema:

1. **Define the schema** for your expected metadata format
2. **Generate a data validator** that checks:
   - All required fields are present
   - Data types match
   - Enum values are in the allowed list
   - Validation rules are satisfied
3. **Run validation** on submitted files before accepting

### Use Case 4: Generating Documentation

You want to create human-readable documentation from schemas:

1. **Maintain schemas** as JSON files
2. **Generate HTML/PDF docs** that show:
   - Table of attributes with descriptions
      - Valid values for enums
   - Examples for each field
3. **Share with data collectors** and analysts

## Troubleshooting

### Problem: Auto-generated schema has wrong data types

**Solution:** The script infers types from data. After generation:
1. Review each attribute's dataType
2. Manually correct any misclassifications
3. Consider adjusting --enum-threshold if too many/few enums

### Problem: Enum field has too many values

**Solution:**
1. Increase --enum-threshold when generating
2. Or manually change dataType from "enum" to "string"
3. Remove the validValues array

### Problem: Missing values not handled

**Solution:**
1. Document missing value codes in validationRules
2. Example: "Use -9999 for missing, -8888 for unknown"
3. Mark field as required: false

### Problem: Date fields detected as string

**Solution:**
1. Ensure dates in your data use YYYY-MM-DD format
2. Or manually change dataType to "date" after generation
3. Add validation rule: "Format: YYYY-MM-DD"

## Additional Resources

- **LinkML Schema**: `/modules/shared/metadata-schema-template.yaml`
- **JSON Schema**: `/json-schemas/MetadataSchema.json`
- **Templates**: `/templates/metadata-schemas/`
- **Auto-generation Script**: `scripts/create_metadata_schema.py`

## Questions or Issues?

If you encounter problems or have questions about metadata schemas, please contact the data model team or open an issue in the repository.
