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


