"""Deterministic ALL ALS dictionary, header, and value-level PHI preflight."""

import csv
from datetime import date, datetime
from pathlib import Path
import re

import yaml


# Complete dates only. A bare year is handled separately as a review warning.
_ISO_DATE = re.compile(r'(?<!\d)(?:19|20)\d{2}[-/.](?:0?[1-9]|1[0-2])[-/.](?:0?[1-9]|[12]\d|3[01])(?!\d)')
_SLASH_DATE = re.compile(r'(?<!\d)(?:0?[1-9]|1[0-2])[-/](?:0?[1-9]|[12]\d|3[01])[-/](?:19|20)\d{2}(?!\d)')
_TEXT_DATE = re.compile(
    r'(?i)(?<!\w)(?:(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|'
    r'jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+'
    r'\d{1,2}(?:st|nd|rd|th)?[,]?\s+(?:19|20)\d{2}|\d{1,2}\s+'
    r'(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|'
    r'aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(?:19|20)\d{2})(?!\w)'
)
_BARE_YEAR = re.compile(r'(?<![\w\d])(19\d{2}|20\d{2})(?![\w\d])')


def normalize(value):
    """Conservative comparison key for views and column names."""
    value = str(value or '').lstrip('\ufeff').strip().casefold()
    return re.sub(r'[\s_-]+', '_', value).strip('_')


def _unique(values, label):
    result = []
    seen = set()
    for value in values or []:
        key = normalize(value)
        if not key:
            raise ValueError(f'{label} cannot contain an empty value')
        if key in seen:
            raise ValueError(f'{label} contains duplicate normalized value {key!r}')
        seen.add(key)
        result.append(key)
    return result


def _tabular_rows(path):
    """Return headers and an iterator of values; callers must not log values."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in ('.csv', '.tsv', '.txt'):
        stream = open(path, newline='', encoding='utf-8-sig')
        reader = csv.reader(stream, delimiter='\t' if suffix == '.tsv' else ',')
        headers = next(reader, [])

        def rows():
            try:
                yield from reader
            finally:
                stream.close()

        return headers, rows()
    if suffix in ('.xlsx', '.xls'):
        try:
            import openpyxl
            workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        except ImportError as error:
            raise ValueError(f'Cannot inspect Excel file {path}: openpyxl is required') from error
        sheet_rows = workbook.active.iter_rows(values_only=True)
        headers = list(next(sheet_rows, []) or [])

        def rows():
            try:
                yield from sheet_rows
            finally:
                workbook.close()

        return headers, rows()
    raise ValueError(f'Unsupported ALL ALS preflight file type: {path.name}')


def read_headers(path, *, allow_leading_empty_index=False, return_index_warning=False):
    """Read tabular headers without reading/logging data values."""
    headers, rows = _tabular_rows(path)
    # CSV streams and workbooks are opened even when only inspecting headers.
    # Start then close the iterator so CSV streams/workbooks are released even
    # though only the header row is needed here.
    try:
        next(rows, None)
    finally:
        close = getattr(rows, 'close', None)
        if close:
            close()
    normalized = [normalize(header) for header in headers]
    ignored_index = False
    if allow_leading_empty_index and normalized and not normalized[0]:
        normalized = normalized[1:]
        ignored_index = True
    normalized = _unique(normalized, f'headers in {Path(path).name}')
    if not normalized:
        raise ValueError(f'No substantive headers found in {Path(path).name}')
    if return_index_warning:
        return normalized, ignored_index
    return normalized


def load_dictionary(path, *, view_column='View Name', field_column='Field',
                    description_column='Description', value_column='Values',
                    definition_value_markers=('', 'NA')):
    """Parse sparse/populated views and contiguous field/value-definition blocks."""
    rows = _read_dictionary_rows(path)
    if not rows:
        raise ValueError('ALL ALS data dictionary is empty')
    required = {view_column, field_column, description_column, value_column}
    absent = required - set(rows[0])
    if absent:
        raise ValueError(f'ALL ALS data dictionary missing required columns: {sorted(absent)}')
    markers = {str(marker).strip().casefold() for marker in definition_value_markers}
    if not markers:
        raise ValueError('definition_value_markers cannot be empty')
    views, current_view, active_field = {}, None, {}
    for number, row in enumerate(rows, 2):
        raw_view = str(row.get(view_column) or '').strip()
        raw_field = str(row.get(field_column) or '').strip()
        raw_description = str(row.get(description_column) or '').strip()
        raw_value = str(row.get(value_column) or '').strip()
        if raw_view:
            current_view = normalize(raw_view)
            if not current_view:
                raise ValueError(f'Dictionary row {number}: empty normalized view name')
            if current_view in views and views[current_view]['display_name'] != raw_view:
                raise ValueError(f'Dictionary row {number}: conflicting spellings for view {current_view!r}')
            views.setdefault(current_view, {'display_name': raw_view, 'fields': set(), 'definitions': {}, 'warnings': []})
        if not current_view:
            if raw_field or raw_value or raw_description:
                raise ValueError(f'Dictionary row {number}: content appears before a view name')
            continue
        view = views[current_view]
        field = normalize(raw_field) if raw_field else active_field.get(current_view)
        if not field:
            if raw_value or raw_description:
                raise ValueError(f'Dictionary row {number}: value appears before a field definition')
            continue
        is_new = field not in view['fields']
        if is_new:
            if not raw_field:
                raise ValueError(f'Dictionary row {number}: value appears before a field definition')
            if raw_value.casefold() not in markers:
                raise ValueError(f'Dictionary row {number}: first definition of {raw_field!r} must use a definition value marker')
            view['fields'].add(field)
            view['definitions'][field] = {'display_name': raw_field, 'description': raw_description,
                                          'values': {}, 'ambiguous_values': {}}
            active_field[current_view] = field
            continue
        if field != active_field.get(current_view):
            raise ValueError(f'Dictionary row {number}: non-contiguous repeated field {raw_field!r} in {view["display_name"]!r}')
        if not raw_value:
            raise ValueError(f'Dictionary row {number}: repeated field {raw_field or field!r} has no value code')
        if not raw_description:
            raise ValueError(f'Dictionary row {number}: value {raw_value!r} for {field!r} has no description')
        definition = view['definitions'][field]
        values, ambiguous = definition['values'], definition['ambiguous_values']
        if raw_value in ambiguous:
            if raw_description in ambiguous[raw_value]:
                view['warnings'].append(f'Dictionary row {number}: duplicate value/description {raw_value!r} for {field!r}; ignored')
            else:
                ambiguous[raw_value].append(raw_description)
        elif raw_value in values:
            if values[raw_value] == raw_description:
                view['warnings'].append(f'Dictionary row {number}: duplicate value/description {raw_value!r} for {field!r}; ignored')
                continue
            if raw_value != 'NA':
                raise ValueError(f'Dictionary row {number}: conflicting descriptions for value {raw_value!r} in {field!r}')
            ambiguous[raw_value] = [values.pop(raw_value), raw_description]
        else:
            values[raw_value] = raw_description
    if not views or any(not value['fields'] for value in views.values()):
        raise ValueError('Every ALL ALS dictionary view must contain at least one field')
    return views


def _read_dictionary_rows(path):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == '.csv':
        with open(path, newline='', encoding='utf-8-sig') as stream:
            return list(csv.DictReader(stream))
    if suffix in ('.xlsx', '.xls'):
        try:
            import openpyxl
            workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
            rows = workbook.active.iter_rows(values_only=True)
            headers = next(rows, None)
            result = [dict(zip(headers, row)) for row in rows]
            workbook.close()
            return result
        except ImportError as error:
            raise ValueError(f'Cannot inspect Excel dictionary {path}: openpyxl is required') from error
    raise ValueError(f'Unsupported ALL ALS data dictionary type: {path.name}')


def load_policy(path):
    try:
        with open(path) as stream:
            policy = yaml.safe_load(stream) or {}
    except FileNotFoundError as error:
        raise ValueError(f'ALL ALS PHI/PII policy file not found: {path}') from error
    if policy.get('version') != 1 or not isinstance(policy.get('forbidden_columns'), list):
        raise ValueError('ALL ALS PHI/PII policy must have version: 1 and forbidden_columns list')
    return set(_unique(policy['forbidden_columns'], 'forbidden_columns'))


def load_date_policy(path):
    try:
        with open(path) as stream:
            policy = yaml.safe_load(stream) or {}
    except FileNotFoundError as error:
        raise ValueError(f'ALL ALS date-screening policy file not found: {path}') from error
    allowed = policy.get('allowed_columns')
    if policy.get('version') != 1 or not isinstance(allowed, dict):
        raise ValueError('ALL ALS date-screening policy must have version: 1 and allowed_columns mapping')
    if (set(allowed) - {'all_files', 'by_view', 'by_view_prefix'}
            or not isinstance(allowed.get('all_files', []), list)
            or not isinstance(allowed.get('by_view', {}), dict)
            or not isinstance(allowed.get('by_view_prefix', {}), dict)):
        raise ValueError(
            'ALL ALS date-screening policy allowed_columns must contain all_files list and/or '
            'by_view/by_view_prefix mappings'
        )
    return {
        'all_files': set(_unique(allowed.get('all_files', []), 'date allowed all_files columns')),
        'by_view': {normalize(view): set(_unique(columns, f'date allowed columns for {view!r}'))
                    for view, columns in allowed.get('by_view', {}).items()},
        'by_view_prefix': {
            normalize(prefix): set(_unique(columns, f'date allowed columns for view prefix {prefix!r}'))
            for prefix, columns in allowed.get('by_view_prefix', {}).items()
        },
    }


def _has_complete_date(value):
    if isinstance(value, (datetime, date)):
        return True
    if not isinstance(value, str):
        return False
    return bool(_ISO_DATE.search(value) or _SLASH_DATE.search(value) or _TEXT_DATE.search(value))


def _has_bare_year(value):
    return isinstance(value, str) and bool(_BARE_YEAR.search(value))


def _format_locations(locations, *, include_values=False):
    if include_values:
        # This path is deliberately opt-in because values can be PHI. repr()
        # keeps embedded newlines on one terminal/report line.
        return f'{len(locations)} cells (' + '; '.join(
            f'row {row}: {value!r}' for row, value in locations
        ) + ')'
    rows = ', '.join(str(row) for row in locations[:10])
    extra = f'; +{len(locations) - 10} more' if len(locations) > 10 else ''
    return f'{len(locations)} cells (rows {rows}{extra})'


def _write_markdown_report(path, failures, warnings, file_count):
    """Write a value-free preflight report for sharing with data submitters."""
    lines = ['# ALL ALS Preflight Report', '']
    if failures:
        lines.extend(['**Status:** Failed', ''])
    else:
        lines.extend(['**Status:** Passed', ''])
    lines.extend([f'**Staged files checked:** {file_count}', ''])
    if failures:
        lines.extend(['## Blocking findings', ''])
        for filename, view, issues in failures:
            lines.extend([f'### `{filename}` → `{view}`', ''])
            lines.extend(f'- {issue}' for issue in issues)
            lines.append('')
    if warnings:
        lines.extend(['## Warnings', ''])
        lines.extend(f'- {warning}' for warning in warnings)
        lines.append('')
    if not failures and not warnings:
        lines.extend(['No blocking findings or warnings.', ''])
    try:
        report = Path(path)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text('\n'.join(lines), encoding='utf-8')
    except OSError as error:
        raise ValueError(f'Could not write ALL ALS preflight report: {error}') from error


def _scan_date_values(path, *, allowed_columns, allow_leading_empty_index,
                      include_values=False):
    """Return safe, aggregated blocking dates and non-blocking bare-year warnings."""
    headers, rows = _tabular_rows(path)
    normalized = [normalize(header) for header in headers]
    if allow_leading_empty_index and normalized and not normalized[0]:
        normalized = normalized[1:]
        offset = 1
    else:
        offset = 0
    dates, years = {}, {}
    try:
        for row_number, row in enumerate(rows, 2):
            for column, value in zip(normalized, row[offset:]):
                if not column or value is None or value == '' or column in allowed_columns:
                    continue
                if _has_complete_date(value):
                    dates.setdefault(column, []).append(
                        (row_number, value) if include_values else row_number
                    )
                elif _has_bare_year(value):
                    years.setdefault(column, []).append(
                        (row_number, value) if include_values else row_number
                    )
    finally:
        close = getattr(rows, 'close', None)
        if close:
            close()
    return dates, years


def validate(staging, paths, views, settings):
    """Return safe preflight warnings or raise one grouped error after all files scan."""
    ignored = set(_unique(settings.get('ignored_file_columns', []), 'ignored_file_columns'))
    dictionary_exceptions = set(_unique(settings.get('dictionary_exceptions', []),
                                        'dictionary exception fields'))
    dictionary_views = {normalize(view): value for view, value in settings['dictionary_views'].items()}
    if len(dictionary_views) != len(settings['dictionary_views']):
        raise ValueError('Dictionary contains duplicate normalized view names')
    required_all = set(_unique((settings.get('required_columns') or {}).get('all_files', []), 'required all_files columns'))
    required_by_view = {normalize(view): set(_unique(columns, f'required columns for {view!r}'))
                        for view, columns in ((settings.get('required_columns') or {}).get('by_view') or {}).items()}
    if not set(required_by_view) <= set(dictionary_views):
        raise ValueError(f'Required-column configuration names unknown dictionary views: {sorted(set(required_by_view) - set(dictionary_views))}')
    forbidden = load_policy(settings['phi_pii_columns_file'])
    date_policy = load_date_policy(settings['date_screening_policy_file'])
    if not set(date_policy['by_view']) <= set(dictionary_views):
        raise ValueError(f'Date-policy configuration names unknown dictionary views: {sorted(set(date_policy["by_view"]) - set(dictionary_views))}')
    configured_dates = (date_policy['all_files']
                        | set().union(*date_policy['by_view'].values(), set())
                        | set().union(*date_policy['by_view_prefix'].values(), set()))
    conflicts = (ignored | required_all | set().union(*required_by_view.values(), set()) | configured_dates) & forbidden
    if conflicts:
        raise ValueError(f'ALL ALS preflight configuration conflicts with PHI/PII policy: {sorted(conflicts)}')

    failures, warnings = [], []
    for view, definition in sorted(dictionary_views.items()):
        deprecated = sorted(definition['fields'] & dictionary_exceptions)
        if deprecated:
            warnings.append(
                f'{definition["display_name"]}: dictionary includes exception field(s): '
                + ', '.join(deprecated)
            )
    for source_id, file_data in staging.items():
        filename = next(iter(file_data))
        view = normalize(views.get(source_id, ''))
        issues = []
        display_view = dictionary_views.get(view, {}).get('display_name', view or '<empty>')
        if view not in dictionary_views:
            issues.append(f'no data-dictionary view named {view!r}')
        path = paths.get(source_id)
        if not path:
            issues.append('file could not be downloaded for validation')
        if path:
            try:
                headers, ignored_index = read_headers(path, allow_leading_empty_index=settings.get('allow_leading_empty_index', True), return_index_warning=True)
                headers = set(headers)
                if ignored_index:
                    warnings.append(f'{filename}: ignored leading unnamed row-index column')
                forbidden_headers = sorted(headers & forbidden)
                if forbidden_headers:
                    issues.append('forbidden PHI/PII headers: ' + ', '.join(forbidden_headers))
                missing_required = sorted((required_all | required_by_view.get(view, set())) - headers)
                if missing_required:
                    issues.append('required headers missing: ' + ', '.join(missing_required))
                if view in dictionary_views:
                    substantive = headers - ignored
                    # Technical file identifiers and legacy dictionary exceptions
                    # are intentionally outside exact dictionary coverage.
                    expected = dictionary_views[view]['fields'] - ignored - dictionary_exceptions
                    extras, missing = sorted(substantive - expected), sorted(expected - substantive)
                    if extras:
                        issues.append('file headers absent from dictionary: ' + ', '.join(extras))
                    if missing:
                        issues.append('dictionary headers absent from file: ' + ', '.join(missing))
                allowed_dates = (date_policy['all_files'] | date_policy['by_view'].get(view, set())
                                 | set().union(*(columns for prefix, columns in date_policy['by_view_prefix'].items()
                                                  if view.startswith(prefix)), set()))
                include_values = settings.get('include_violation_values', False)
                dates, years = _scan_date_values(
                    path, allowed_columns=allowed_dates,
                    allow_leading_empty_index=settings.get('allow_leading_empty_index', True),
                    include_values=include_values,
                )
                if dates:
                    issues.append('disallowed date values: ' + '; '.join(
                        f'{column}: {_format_locations(rows, include_values=include_values)}'
                        for column, rows in sorted(dates.items())))
                for column, rows in sorted(years.items()):
                    warnings.append(
                        f'{filename}: standalone year warning in {column}: '
                        f'{_format_locations(rows, include_values=include_values)}'
                    )
            except Exception as error:
                # A malformed/unreadable file is a recorded per-file failure;
                # continue validating every other staged file.
                issues.append(f'file could not be fully validated: {error}')
        if issues:
            failures.append((filename, display_view, issues))
    report_path = settings.get('preflight_report')
    if report_path:
        _write_markdown_report(report_path, failures, warnings, len(staging))
    if failures:
        lines = ['ALL ALS preflight failed']
        for filename, view, issues in failures:
            lines.append(f'\n{filename} → {view}')
            lines.extend(f'  - {issue}' for issue in issues)
        if warnings:
            lines.append('\nWarnings')
            lines.extend(f'  - {warning}' for warning in warnings)
        raise ValueError('\n'.join(lines))
    return warnings
