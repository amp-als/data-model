# NIH CADR Compliance Guide

## Overview

This document explains how the AMP-ALS metadata schema system complies with **NIH Common Access to Data and Resources (CADR) requirements** for metadata collection and public availability.

## NIH CADR Requirement

**Standard:** To the extent possible, Intramural repository staff or NIH-funded entities and contractors responsible for NIH CADR operations must collect and make publicly available metadata to enable discovery, reuse, and citation of datasets, using schema that are appropriate to, and ideally widely used across, the community(ies) the repository serves.

### Applicability
- Repositories
- NIH-funded data repositories
- AMP-ALS Data Portal

### Steps to Comply

1. **Identify metadata schema** that are appropriate to, and ideally widely used across, the community(ies) the repository serves
2. **Ensure that relevant metadata is exposed** to enable discovery, reuse, and citation of datasets
3. **Email ICO ISSO with evidence** (screenshots of adopted metadata schema)

## How This System Complies

### 1. Community Standards Alignment

Our metadata schema system aligns with widely-used community standards:

#### DataCite Metadata Schema v4.4
**Purpose:** Standard for dataset citation and persistent identifiers
**Community:** Global research data community
**Our Support:**
- Mandatory DataCite properties: Identifier, Creator, Title, Publisher, PublicationYear, ResourceType
- Recommended properties: Subject, Contributor, Date, RelatedIdentifier, Description, Rights, FundingReference
- All DataCite-required fields are included in our MetadataSchema class

**Reference:** https://schema.datacite.org/meta/kernel-4.4/

#### Dublin Core Metadata Initiative (DCMI)
**Purpose:** Core metadata elements for resource description
**Community:** Libraries, archives, scholarly repositories
**Our Support:**
- Core elements: Title, Creator, Subject, Description, Publisher, Contributor, Date, Type, Identifier, Rights
- Our schema includes all 15 Dublin Core elements

**Reference:** http://purl.org/dc/terms/

#### Data Catalog Vocabulary (DCAT)
**Purpose:** W3C standard for data catalogs
**Community:** Government, research, and open data communities
**Our Support:**
- Dataset properties: title, description, creator, publisher, identifier, keyword, license, issued, modified
- Distribution properties: accessURL, format
- DCAT-compliant for dataset discovery

**Reference:** https://www.w3.org/TR/vocab-dcat-2/

#### Schema.org Dataset
**Purpose:** Structured data for web-based discovery
**Community:** Search engines, web platforms
**Our Support:**
- Compatible with Schema.org Dataset type
- Supports Google Dataset Search indexing
- Enables rich snippets in search results

**Reference:** https://schema.org/Dataset

### 2. Enabling Discovery, Reuse, and Citation

Our metadata schema includes fields that specifically enable:

#### Discovery
- **Title** - Primary dataset name for search
- **Description** - Detailed content description
- **Subjects/Keywords** - Controlled vocabulary terms for topic-based discovery
- **Identifier** - Persistent identifier (DOI) for reliable access
- **LandingPage** - URL to dataset entry point
- **Publisher** - Institutional affiliation for filtering

#### Reuse
- **License** - Clear usage rights (CC-BY, CC-BY-NC, etc.)
- **LicenseURL** - Link to full license terms
- **AccessRights** - Information about access requirements (Open, Controlled, etc.)
- **ContactEmail** - Support for questions
- **Format** - File format information for compatibility
- **Version** - Version tracking for reproducibility

#### Citation
- **Creators** - Authors with ORCID identifiers
- **Contributors** - Additional contributors with roles
- **PublicationYear** - Year of public availability
- **Publisher** - Publishing institution
- **Identifier** - DOI or other persistent identifier
- **CitationRecommendation** - Preferred citation format
- **RelatedPublications** - Connected research articles
- **FundingReferences** - Funding acknowledgment

### 3. Evidence for Compliance

The following provides evidence of our adopted metadata schema:

#### Schema Definition
- **Location:** `/modules/shared/metadata-schema-template.yaml`
- **Format:** LinkML (Linked Data Modeling Language)
- **Standards Compliance:** Explicitly declares conformance to DataCite, Dublin Core, DCAT via `conformsTo` field

#### Generated JSON Schema
- **Location:** `/json-schemas/MetadataSchema.json`
- **Format:** JSON Schema (Draft 07)
- **Use:** Validates metadata submissions

#### Example Implementation
- **Location:** `/templates/metadata-schemas/dataset_with_citation_example.json`
- **Demonstrates:** Complete dataset citation metadata with attribute definitions

## Using Citation Metadata

### Required Fields for NIH CADR Compliance

At minimum, include these fields for dataset-level metadata:

```json
{
  "schemaName": "YourDatasetName",
  "schemaType": "clinical",
  "version": "1.0",
  "description": "Detailed description of dataset content and purpose",

  "identifier": "10.7303/synXXXXXXX",
  "identifierType": "DOI",
  "title": "Full Dataset Title",
  "creators": ["LastName, FirstName (ORCID)"],
  "publisher": "Institution Name",
  "publicationYear": 2024,
  "subjects": ["keyword1", "keyword2", "keyword3"],
  "license": "CC-BY-4.0",
  "accessRights": "Open",

  "attributes": [...]
}
```

### Recommended Additional Fields

For comprehensive compliance, also include:

- **conformsTo** - List standards you align with
- **contributors** - Data collectors, curators
- **fundingReferences** - Grant acknowledgments
- **relatedPublications** - Associated papers
- **contactEmail** - Support contact
- **datePublished** - Publication date
- **citationRecommendation** - How to cite

### Complete Example

See `/templates/metadata-schemas/dataset_with_citation_example.json` for a full example with:
- Dataset-level citation metadata
- Attribute definitions for data columns
- Alignment with DataCite, Dublin Core, and DCAT standards

## Field Mapping to Standards

| Our Field | DataCite | Dublin Core | DCAT | Schema.org |
|-----------|----------|-------------|------|------------|
| identifier | Identifier | identifier | identifier | identifier |
| title | Title | title | title | name |
| creators | Creator | creator | creator | creator |
| description | Description | description | description | description |
| subjects | Subject | subject | keyword | keywords |
| publisher | Publisher | publisher | publisher | publisher |
| publicationYear | PublicationYear | date | issued | datePublished |
| license | Rights | rights | license | license |
| contributors | Contributor | contributor | - | contributor |
| version | Version | - | version | version |
| fundingReferences | FundingReference | - | - | funder |

## Controlled Vocabularies

Use these controlled vocabularies when possible for better interoperability:

### Subject/Keywords
- **MeSH (Medical Subject Headings)** - https://meshb.nlm.nih.gov/
- **SNOMED CT** - https://www.snomed.org/
- **Human Phenotype Ontology (HPO)** - https://hpo.jax.org/
- **Mondo Disease Ontology** - https://mondo.monarchinitiative.org/

### Resource Types
- Use DataCite Resource Type General values
- Our ResourceTypeEnum aligns with DataCite

### Access Rights
- Use standardized terms: Open, Restricted, Embargoed, Controlled
- Our AccessRightsEnum provides these values

### Licenses
- Use SPDX license identifiers when possible
- Common choices: CC-BY-4.0, CC-BY-NC-4.0, CC0-1.0
- See: https://spdx.org/licenses/

## Validation

### Validate Your Metadata

Use the generated JSON Schema to validate your metadata:

```bash
# Install JSON schema validator
pip install jsonschema

# Validate your metadata file
jsonschema -i your_metadata.json json-schemas/MetadataSchema.json
```

### Programmatic Validation

```python
import json
import jsonschema

# Load schemas
with open('json-schemas/MetadataSchema.json') as f:
    schema = json.load(f)

with open('your_metadata.json') as f:
    metadata = json.load(f)

# Validate
try:
    jsonschema.validate(metadata, schema)
    print("✓ Metadata is valid and CADR-compliant!")
except jsonschema.ValidationError as e:
    print(f"✗ Validation error: {e.message}")
```

## Publishing Metadata

### Make Metadata Publicly Available

1. **Include in Dataset Repository**
   - Upload metadata JSON file alongside data files
   - Name clearly: `dataset_metadata.json` or `METADATA.json`

2. **Register with DataCite**
   - If you have a DOI, register metadata with DataCite
   - Use DataCite API or repository integration

3. **Submit to Data Catalogs**
   - Submit to NIH GDS (Genomic Data Sharing)
   - Include in institutional repositories
   - List in domain-specific registries

4. **Enable Web Discovery**
   - Add Schema.org structured data to landing pages
   - Enables Google Dataset Search indexing

### Landing Page Requirements

Your dataset landing page should display:
- Title, creators, publication year
- Description/abstract
- License and access rights
- DOI/persistent identifier
- Contact information
- Download/access instructions
- Recommended citation

## Compliance Checklist

Use this checklist to verify CADR compliance:

- [ ] Metadata schema identified and documented
- [ ] Schema aligns with community standards (DataCite, Dublin Core, DCAT)
- [ ] All mandatory citation fields included:
  - [ ] Identifier (DOI preferred)
  - [ ] Title
  - [ ] Creators
  - [ ] Publisher
  - [ ] Publication Year
  - [ ] Description
  - [ ] Subjects/Keywords
  - [ ] License
  - [ ] Access Rights
- [ ] Metadata enables discovery (title, description, keywords)
- [ ] Metadata enables reuse (license, format, contact)
- [ ] Metadata enables citation (creators, DOI, recommended citation)
- [ ] Metadata is publicly available
- [ ] Metadata validation implemented
- [ ] Documentation provided for data submitters

## References

### Standards Documentation
- DataCite Metadata Schema: https://schema.datacite.org/
- Dublin Core Metadata Terms: http://purl.org/dc/terms/
- DCAT Vocabulary: https://www.w3.org/TR/vocab-dcat-2/
- Schema.org Dataset: https://schema.org/Dataset

### NIH Resources
- NIH CADR Policy: https://sharing.nih.gov/
- NIH Data Management and Sharing: https://grants.nih.gov/grants/guide/notice-files/NOT-OD-21-013.html
- Generalist Repository Ecosystem Initiative (GREI): https://datascience.nih.gov/data-ecosystem/

### Tools
- LinkML: https://linkml.io/
- JSON Schema: https://json-schema.org/
- DataCite DOI Registration: https://datacite.org/

## Questions?

For questions about NIH CADR compliance or metadata schema:
- Review the metadata schema guide: `/docs/metadata-schema-guide.md`
- Check example schemas: `/templates/metadata-schemas/`
- Contact the AMP-ALS data team
