#!/usr/bin/env python3
"""
Complete workflow for SRA SAMI dataset harmonization and Synapse annotation.

This script:
1. Harmonizes SRA metadata to ALS data model standards
2. Annotates individual FASTQ files with sample metadata 
3. Creates dataset entity with dataset-level annotations
4. Organizes files and adds to dataset
5. Creates wiki content for dataset description
6. Adds dataset to collection for portal publication

Usage:
    python scripts/sra_sami_workflow.py --project-id syn12345 --staging-folder syn67890
"""

import argparse
import csv
import json
import pandas as pd
import synapseclient
from pathlib import Path
from typing import Dict, List, Any
import re

class SRAWorkflow:
    def __init__(self, syn_client: synapseclient.Synapse, project_id: str, staging_folder: str):
        self.syn = syn_client
        self.project_id = project_id
        self.staging_folder = staging_folder
        
        # Load dataset schema for validation
        with open('json-schemas/Dataset.json', 'r') as f:
            self.dataset_schema = json.load(f)
    
    def harmonize_metadata(self) -> pd.DataFrame:
        """Harmonize SRA metadata to ALS data model standards."""
        print("🔄 Harmonizing SRA metadata...")
        
        # Load raw metadata
        raw_df = pd.read_csv('metadata/raw/SRA_SAMI/SraRunTable.csv')
        
        # Create harmonized dataframe
        harmonized_data = []
        
        for _, row in raw_df.iterrows():
            # Extract treatment groups from sample names
            sample_name = row['Sample Name']
            treatment_match = re.search(r'(Halo|Apobec-YTH|Apobec-YTHmut)', row['treatment'])
            treatment = treatment_match.group(1) if treatment_match else 'Unknown'
            
            harmonized_row = {
                # File identification
                'run_id': row['Run'],
                'experiment_id': row['Experiment'],
                'sample_name': sample_name,
                'biosample_id': row['BioSample'],
                
                # Subject/Sample annotations
                'globalSubjectId': f"sra:{row['SRA Study']}:{sample_name}",
                'originalSubjectId': sample_name,
                'datasetReference': row['SRA Study'], 
                'dataSourcePrefix': 'sra',
                
                # Assay annotations
                'assayType': 'RNA-seq',
                'platform': 'Illumina NovaSeq 6000',
                'libraryLayout': 'Paired End',
                'librarySelection': row['LibrarySelection'],
                'librarySource': row['LibrarySource'],
                
                # Biological annotations
                'species': 'Homo sapiens',
                'sex': 'Female',  # All samples are female based on data
                'cellLine': row['cell_line'],
                'tissue': 'Cell line',  # HEK293T cells
                'treatment': treatment,
                'replicate': row['replicate'],
                
                # Technical annotations
                'fileFormat': 'FASTQ',
                'dataType': 'RNA-seq',
                'instrument': row['Instrument'],
                'readLength': row['AvgSpotLen'],
                'totalBases': row['Bases'],
                'totalBytes': row['Bytes'],
                
                # Provenance
                'bioProject': row['BioProject'],
                'centerName': row['Center Name'],
                'releaseDate': row['ReleaseDate'],
                'biomaterialProvider': row['BIOMATERIAL_PROVIDER']
            }
            harmonized_data.append(harmonized_row)
        
        harmonized_df = pd.DataFrame(harmonized_data)
        
        # Save harmonized metadata
        output_path = 'metadata/standardized/SRA_SAMI/SRA_SAMI_harmonized_metadata.csv'
        harmonized_df.to_csv(output_path, index=False)
        print(f"✅ Saved harmonized metadata to {output_path}")
        
        return harmonized_df
    
    def create_dataset_annotations(self, harmonized_df: pd.DataFrame) -> Dict[str, Any]:
        """Create dataset-level annotations based on harmonized metadata."""
        print("📊 Creating dataset-level annotations...")
        
        # Extract dataset metadata from harmonized data
        unique_treatments = harmonized_df['treatment'].unique().tolist()
        total_samples = len(harmonized_df)
        bio_project = harmonized_df['bioProject'].iloc[0]
        
        dataset_annotations = {
            'title': 'SRA SAMI RNA-seq Dataset - APOBEC and Halo Treatments',
            'description': f'RNA-seq data from HEK293T cells with {", ".join(unique_treatments)} treatments. Contains {total_samples} samples with paired-end sequencing.',
            'creator': ['University of Michigan'],
            'contributor': ['sbarmada@med.umich.edu'],
            'measurementTechnique': ['RNA-seq'],
            'keywords': ['RNA-seq', 'APOBEC', 'Halo', 'HEK293T', 'treatment'],
            'species': ['Homo sapiens'],
            'individualCount': total_samples,
            'studyType': 'experimental',
            'source': 'Sequence Read Archive (SRA)',
            'url': f'https://www.ncbi.nlm.nih.gov/bioproject/{bio_project}',
            'license': 'public',
            'collection': ['National Institutes of Health'],
            'dataSourcePrefix': 'sra'
        }
        
        return dataset_annotations
    
    def annotate_files(self, harmonized_df: pd.DataFrame) -> None:
        """Annotate individual FASTQ files with sample metadata."""
        print("🏷️  Annotating individual FASTQ files...")
        
        # Get all files in staging folder
        staging_entity = self.syn.get(self.staging_folder)
        files = list(self.syn.getChildren(staging_entity, includeTypes=['file']))
        
        print(f"Found {len(files)} files in staging folder")
        
        for file_info in files:
            file_name = file_info['name']
            
            # Match file to metadata by SRR ID
            srr_match = re.search(r'(SRR\d+)', file_name)
            if not srr_match:
                print(f"⚠️  Could not extract SRR ID from {file_name}")
                continue
                
            srr_id = srr_match.group(1)
            
            # Find matching metadata
            sample_data = harmonized_df[harmonized_df['run_id'] == srr_id]
            if sample_data.empty:
                print(f"⚠️  No metadata found for {srr_id}")
                continue
                
            sample_row = sample_data.iloc[0]
            
            # Create file-level annotations
            file_annotations = {
                'dataType': sample_row['dataType'],
                'fileFormat': sample_row['fileFormat'],
                'assayType': sample_row['assayType'],
                'globalSubjectId': sample_row['globalSubjectId'],
                'originalSubjectId': sample_row['originalSubjectId'],
                'run_id': sample_row['run_id'],
                'experiment_id': sample_row['experiment_id'],
                'biosample_id': sample_row['biosample_id'],
                'species': sample_row['species'],
                'sex': sample_row['sex'],
                'cellLine': sample_row['cellLine'],
                'treatment': sample_row['treatment'],
                'replicate': sample_row['replicate'],
                'platform': sample_row['platform'],
                'libraryLayout': sample_row['libraryLayout'],
                'instrument': sample_row['instrument'],
                'readLength': int(sample_row['readLength']),
                'dataSourcePrefix': sample_row['dataSourcePrefix']
            }
            
            # Apply annotations to file
            try:
                self.syn.set_annotations(file_info['id'], annotations=file_annotations)
                print(f"✅ Annotated {file_name} ({srr_id})")
            except Exception as e:
                print(f"❌ Failed to annotate {file_name}: {e}")
    
    def create_dataset_entity(self, dataset_annotations: Dict[str, Any]) -> str:
        """Create dataset entity and apply dataset-level annotations."""
        print("📁 Creating dataset entity...")
        
        # Create dataset folder
        dataset_folder = synapseclient.Folder(
            name='SRA_SAMI_Dataset',
            description=dataset_annotations['description'],
            parent=self.project_id
        )
        
        dataset_folder = self.syn.store(dataset_folder)
        dataset_id = dataset_folder.id
        
        # Apply dataset annotations
        self.syn.set_annotations(dataset_id, annotations=dataset_annotations)
        print(f"✅ Created dataset entity {dataset_id}")
        
        return dataset_id
    
    def organize_files(self, dataset_id: str) -> None:
        """Move files from staging to dataset folder."""
        print("📂 Organizing files in dataset folder...")
        
        # Get all files in staging folder
        staging_entity = self.syn.get(self.staging_folder)
        files = list(self.syn.getChildren(staging_entity, includeTypes=['file']))
        
        for file_info in files:
            try:
                # Move file to dataset folder
                file_entity = self.syn.get(file_info['id'])
                file_entity.parent = dataset_id
                self.syn.store(file_entity, forceVersion=False)
                print(f"✅ Moved {file_info['name']} to dataset")
            except Exception as e:
                print(f"❌ Failed to move {file_info['name']}: {e}")
    
    def create_wiki(self, dataset_id: str, dataset_annotations: Dict[str, Any]) -> None:
        """Create wiki content for dataset description."""
        print("📝 Creating dataset wiki...")
        
        wiki_content = f"""
# {dataset_annotations['title']}

## Description
{dataset_annotations['description']}

## Dataset Details
- **Species**: {', '.join(dataset_annotations['species'])}
- **Sample Count**: {dataset_annotations['individualCount']}
- **Assay Type**: {', '.join(dataset_annotations['measurementTechnique'])}
- **Study Type**: {dataset_annotations['studyType']}
- **Source**: {dataset_annotations['source']}

## Data Summary
This dataset contains paired-end RNA-seq data from HEK293T cells with different treatments:
- APOBEC-YTH treatment
- APOBEC-YTHmut treatment  
- Halo treatment

Each treatment includes biological replicates sequenced on Illumina NovaSeq 6000.

## Data Access
- **Source URL**: [{dataset_annotations['url']}]({dataset_annotations['url']})
- **License**: {dataset_annotations['license']}
- **Collection**: {', '.join(dataset_annotations['collection'])}

## Contact
- **Creator**: {', '.join(dataset_annotations['creator'])}
- **Contributor**: {', '.join(dataset_annotations['contributor'])}

## Keywords
{', '.join(dataset_annotations['keywords'])}
"""
        
        # Create wiki
        wiki = synapseclient.Wiki(
            title=dataset_annotations['title'],
            markdown=wiki_content,
            owner=dataset_id
        )
        
        wiki = self.syn.store(wiki)
        print(f"✅ Created wiki for dataset {dataset_id}")
    
    def add_to_collection(self, dataset_id: str, collection_id: str = None) -> None:
        """Add dataset to collection for portal publication."""
        if not collection_id:
            print("⚠️  Collection ID not provided, skipping collection addition")
            return
            
        print(f"📚 Adding dataset to collection {collection_id}...")
        
        # This would typically involve adding the dataset to a Synapse view or table
        # The exact implementation depends on your portal's collection structure
        print("✅ Dataset ready for collection addition (manual step required)")

def main():
    parser = argparse.ArgumentParser(description='SRA SAMI dataset workflow')
    parser.add_argument('--project-id', required=True, help='Synapse project ID')
    parser.add_argument('--staging-folder', required=True, help='Synapse staging folder ID')
    parser.add_argument('--collection-id', help='Collection ID for portal publication')
    parser.add_argument('--dry-run', action='store_true', help='Run without making changes')
    
    args = parser.parse_args()
    
    # Login to Synapse
    syn = synapseclient.Synapse()
    syn.login()
    
    # Initialize workflow
    workflow = SRAWorkflow(syn, args.project_id, args.staging_folder)
    
    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
    
    try:
        # Step 1: Harmonize metadata
        harmonized_df = workflow.harmonize_metadata()
        
        # Step 2: Create dataset annotations
        dataset_annotations = workflow.create_dataset_annotations(harmonized_df)
        
        if not args.dry_run:
            # Step 3: Annotate files
            workflow.annotate_files(harmonized_df)
            
            # Step 4: Create dataset entity
            dataset_id = workflow.create_dataset_entity(dataset_annotations)
            
            # Step 5: Organize files
            workflow.organize_files(dataset_id)
            
            # Step 6: Create wiki
            workflow.create_wiki(dataset_id, dataset_annotations)
            
            # Step 7: Add to collection
            workflow.add_to_collection(dataset_id, args.collection_id)
            
            print(f"🎉 Workflow completed! Dataset ID: {dataset_id}")
        else:
            print("🔍 Dry run completed - review harmonized metadata and annotations")
            print(f"Dataset annotations preview:")
            print(json.dumps(dataset_annotations, indent=2))
            
    except Exception as e:
        print(f"❌ Workflow failed: {e}")
        raise

if __name__ == '__main__':
    main()