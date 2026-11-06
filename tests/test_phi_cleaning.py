import pytest

from synapse_dataset_manager.phi_cleaning import (
    clean_file,
    resolve_column_map,
    walk_folder_metadata,
    write_column_map,
)


class MetadataOnlySynapse:
    def __init__(self):
        self.get_called = False
        self.children = {
            'synFolder': [
                {'id': 'synFile', 'name': 'root.csv', 'type': 'file'},
                {'id': 'synChild', 'name': 'nested', 'type': 'folder'},
            ],
            'synChild': [{'id': 'synNested', 'name': 'nested.csv', 'type': 'file'}],
        }

    def getChildren(self, entity_id):
        return self.children[entity_id]

    def get(self, *args, **kwargs):
        self.get_called = True
        raise AssertionError('map scaffolding must not fetch file entities')


def test_column_map_scaffold_recurses_without_fetching_file_content(tmp_path):
    syn = MetadataOnlySynapse()
    files = walk_folder_metadata(syn, 'synFolder')

    assert files == {
        'synFile': {'name': 'root.csv', 'path': ''},
        'synNested': {'name': 'nested.csv', 'path': 'nested'},
    }
    output = tmp_path / 'columns.json'
    assert write_column_map(files, output) == {'synFile': [], 'synNested': []}
    assert syn.get_called is False


def test_csv_cleaning_requires_every_designated_header(tmp_path):
    source = tmp_path / 'source.csv'
    destination = tmp_path / 'clean.csv'
    source.write_text('subject,patient_name,age\n1,Alice,35\n', encoding='utf-8')

    clean_file(source, destination, ['patient_name'])
    assert destination.read_text(encoding='utf-8') == 'subject,age\n1,35\n'

    with pytest.raises(ValueError, match='not found'):
        clean_file(source, destination, ['not_a_header'])


def test_csv_cleaning_handles_retained_bare_quotes(tmp_path):
    source = tmp_path / 'source.csv'
    destination = tmp_path / 'clean.csv'
    source.write_text(
        'subject,notes,patient_name\n1,He said "hello",Alice\n', encoding='utf-8'
    )

    clean_file(source, destination, ['patient_name'])

    assert destination.read_text(encoding='utf-8') == (
        'subject,notes\n1,"He said ""hello"""\n'
    )


def test_filename_column_map_keys_must_be_unambiguous():
    files = {
        'syn1': {'name': 'same.csv', 'path': 'one'},
        'syn2': {'name': 'same.csv', 'path': 'two'},
    }
    with pytest.raises(ValueError, match='more than once'):
        resolve_column_map({'same.csv': ['patient_name']}, files)
