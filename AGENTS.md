# AGENTS.md - Development Guide

## Build Commands
- `make all` - Build all artifacts (ALS.jsonld, ALS.yaml, ALS.ttl)
- `make ALS.jsonld` - Build main JSON-LD artifact using retold
- `make ALS.yaml` - Build LinkML YAML from modules using yq
- `make ALS.ttl` - Build Turtle RDF format
- `make Dataset` - Build JSON schema for Dataset entity
- `make linkml_jsonld` - Generate LinkML JSON-LD output
- `make -B` - Force rebuild all targets

## Test Commands
- `pytest` - Run all Python tests (pytest available in mapping/requirements.txt)
- `pytest mapping/test_*.py` - Run specific test file
- `pytest -k "test_name"` - Run single test by name
- `python3 mapping/transform_cpath.py input.json mapping/cpath.jsonata -s json-schemas/Dataset.json` - Test mapping transforms with validation
- `python3 mapping/transform_cpath.py input.json mapping/cpath.jsonata --strict --log-errors errors.json` - Test with strict validation and error logging

## Lint/Format Commands
- No specific linters configured - follow manual style guidelines below
- CI runs `schematic schema convert ALS.jsonld` for validation
- LinkML validation occurs during build process

## Code Style Guidelines
- **YAML**: Use 2-space indentation, follow LinkML schema conventions, include description fields
- **Python**: Follow PEP 8, use type hints, handle exceptions with try/except (not try/catch)
- **File naming**: Use snake_case for Python files, PascalCase for YAML classes
- **Imports**: Group standard library, third-party, local imports separately with blank lines
- **Functions**: Include docstrings with Args/Returns sections, use descriptive names
- **Error handling**: Validate JSON schemas, return meaningful error messages, log validation errors
- **Data model**: Store source in modules/*.yaml, build artifacts in dist/, use multivalued: true for arrays
- **JSONata**: Store mapping expressions in .jsonata files, validate against target schemas

## Project Structure
- Source files: `modules/*.yaml` (LinkML schema definitions)
- Build artifacts: `dist/` and `json-schemas/`
- Mappings: `mapping/` directory with JSONata transforms and Python scripts
- Main output: `ALS.jsonld` (schematic-compatible format)
- CI: `.github/workflows/main-ci.yml` auto-rebuilds artifacts on PR