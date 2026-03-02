# Gemini Code Assistant Context

## Project Overview

This is a [LinkML](https://linkml.io/)-based data model for the AMP-ALS Knowledge Portal. It's designed to harmonize and standardize metadata from multiple ALS research data sources. The project uses a modular and hierarchical architecture to define the data model, with a clear separation of concerns between base schemas, mixins, and domain-specific schemas.

The core technologies used in this project are:

*   **LinkML:** for data modeling.
*   **YAML:** for schema definitions.
*   **Python:** for scripting and data management.
*   **Make:** for automating the build process.
*   **Synapse:** for data storage and management.

## Building and Running

The project uses a `Makefile` to automate the build process. The following commands are available:

*   `make all`: Build all artifacts, including `ALS.jsonld`, `dist/ALS.yaml`, and `ALS.ttl`.
*   `make ALS.jsonld`: Build the main JSON-LD output.
*   `make dist/ALS.yaml`: Build the LinkML YAML format.
*   `make ALS.ttl`: Build the Turtle RDF format.
*   `make <Schema>`: Build the JSON schema for a specific schema (e.g., `make Dataset`, `make ClinicalDataset`).

To run the build process, you'll need to have the required tools installed, including `yq`, `retold`, `gen-json-schema`, and `json-dereference`.

The `synapse_dataset_manager.py` script is used to manage Synapse datasets. It provides a unified workflow for creating, updating, and annotating datasets. To use this script, you'll need to have the `synapseclient` library installed and configured with your Synapse credentials.

## Development Conventions

The project follows a set of development conventions to ensure code quality and consistency:

*   **Modularity:** The data model is organized into modules, with each module having a specific responsibility.
*   **Inheritance and Composition:** The data model uses inheritance and composition to promote code reuse and maintainability.
*   **Clear Naming Conventions:** The project uses clear and consistent naming conventions for files, schemas, and attributes.
*   **Documentation:** The `README.md` file provides a comprehensive overview of the project, including the data model architecture, build process, and development guidelines. The schemas themselves also contain descriptions and notes.
*   **Testing:** The project has a `pytest` configuration, and the `README.md` suggests running tests with `pytest`.
