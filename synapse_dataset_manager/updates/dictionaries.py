"""Explicit column-based dictionary scaffolds, without ALL ALS conventions."""


def build_mapping(path, options, load_rows):
    """Read one field per row; groups are optional and never forward-filled.

    Group annotations use `_groups`; field mappings retain the existing mapping
    format. Conflicting repeated field definitions fail rather than lose data.
    """
    rows = load_rows(path)
    field_column = options.get('dictionary_field_column', 'Field')
    group_column = options.get('dictionary_group_column')
    description_column = options.get('dictionary_description_column', 'Description')
    result = {'_groups': {}}
    for number, row in enumerate(rows, 2):
        required = [field_column] + ([group_column] if group_column else [])
        for column in required:
            if column not in row:
                raise ValueError(f'Dictionary is missing column {column!r}')
        field = str(row[field_column] or '').strip()
        if not field or field.startswith('_'):
            raise ValueError(f'Dictionary row {number}: invalid field name {field!r}')
        group = str(row[group_column] or '').strip() if group_column else ''
        if group_column and not group:
            raise ValueError(f'Dictionary row {number}: empty group')
        if group:
            result['_groups'].setdefault(group, {})
        entry = {'description': str(row.get(description_column) or '').strip(),
                 'target': '', 'values': {}}
        if field in result and result[field] != entry:
            raise ValueError(f'Conflicting dictionary definitions for {field!r}')
        result[field] = entry
    return result


def apply_group_annotations(template, group, mapping):
    """Fill missing slots only, with exact group matching and no view annotation."""
    result = dict(template)
    for field, value in mapping.get('_groups', {}).get(group, {}).items():
        if field.startswith('_'):
            raise ValueError('Dictionary group annotations cannot set internal control fields')
        if result.get(field) in (None, '', [], ['']) and value not in (None, '', [], ['']):
            result[field] = value
    return result
