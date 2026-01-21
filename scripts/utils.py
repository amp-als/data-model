import synapseclient
from synapseclient.models import (
    File, Folder, Project, Table, EntityView, Dataset,
    DatasetCollection, MaterializedView, SubmissionView
)
 
## bulk move 
def bulk_move_to_folder(source_folder, target_folder): 
    source_folder="syn71824454"
    folder = Folder(id=source_folder)
    folder = folder.sync_from_synapse(download_file=False, recursive=True)
    results=folder.files
    for item in results:
    file = File(id=item.id, download_file=False).get()
    if "v_ALLALS_PR" in str(file.name):
        file.parent_id = target_folder 
        file = file.store()
        print(f"Moved file {file.name} to new folder {file.parent_id}")

def mv_synapse(target, destination, versioning):
    # target = synid of file/folder to be moved
    # destination = synid of parent folder that file/folder will be moved into 
#check that parent_id points to a Folder and not a File; If file, throw exception``
    # using synid, check the type of the synid entity. 
    # if synid.type == File: 
        # change parent_id for synid to parent_id
    # elif synid.type = Folder:
        # change parent_id for synid to parent_id 
    # else: throw exception and say synid doesn't correspond to a folder or file

    # Add rename here as well? so its similar to bash commands
    # versioning = True/False for whether change should cause version change



from synapseclient.api import delete_entity
import asyncio


def delete_file_versions(synid_list:list, version_range:tuple, exceptions:list):
    for synid in synid_list:
        for version in range(version_range):
            try:
                if version != exceptions:
                    async def delete_file_version():
                         await delete_entity(entity_id=synid, version_number=version)
                    #print(f"Deleting version {version} of {synid}")
                    asyncio.run(delete_file_version())
            except Exception as e:
                print(f"Could not delete version {version} of {synid}: {e}")


def validate_annoations(): 



def annotate_synapse(annotations, target, action, versioning):
    # annotations = annotations to be applied
    # target = file/folder/dataset that annotations should be applied to 
    # action = whether we are appending, replacing, or deleting. Deleting will be special case. 
    # versioning = True/False for whether change should cause version change



def add_dataset_columns():
def reorder_dataset_columns():

def create_dataset_entity(): 
    # should give user args to add dataset columns to dataset entity created and reorder them in the same function.  

def add_dataset_to_collection():

def snapshot(): 

def release_dataset():

