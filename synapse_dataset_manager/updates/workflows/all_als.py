"""Explicit ALL ALS form/view identity policy and mandatory header preflight."""

from pathlib import Path

from synapse_dataset_manager.updates import all_als_preflight
from synapse_dataset_manager.updates import all_als_match_manifest


_DEFAULT_DATE_POLICY = Path(__file__).resolve().parents[3] / 'configs' / 'all_als_date_screening.yaml'


def prepare(syn, staging, directory, options, services):
    if options.get('identity_manifest') or options.get('name_column'):
        raise ValueError('Generic identity options require workflow general')
    if not options.get('data_dict_path'):
        raise ValueError('ALL ALS update requires --data-dict or dataset data_dict configuration')
    _, names, paths, groups = services.build_staging_form_map(
        syn, staging, directory, extract_form_names=True,
    )
    defaults = {
        'dictionary': {
            'view_column': 'View Name',
            'field_column': 'Field',
            # Required technical identifiers are not dictionary fields.
            'ignored_file_columns': ['Form Name', 'NeuroGUID', 'NeuroSTAmP', 'visit_name'],
        },
        # Legacy dictionary fields tolerated only in dictionaries, with warnings.
        'dictionary_exceptions': [
            'localUID', 'subjectUID', 'siteUID', 'initials',
            'reason_for_failure', 'state', 'visit',
        ],
        'required_columns': {
            'all_files': ['NeuroGUID', 'NeuroSTAmP'],
            # Dataset-specific demographic view requirements belong in config.
            'by_view': {},
        },
    }
    configured = dict(options.get('all_als') or {})
    settings = {**defaults, **configured}
    configured_dictionary = dict(configured.get('dictionary') or {})
    settings['dictionary'] = {**defaults['dictionary'], **configured_dictionary}
    settings['dictionary']['ignored_file_columns'] = list(dict.fromkeys(
        defaults['dictionary']['ignored_file_columns']
        + list(configured_dictionary.get('ignored_file_columns') or [])
    ))
    settings['dictionary_exceptions'] = list(dict.fromkeys(
        defaults['dictionary_exceptions'] + list(configured.get('dictionary_exceptions') or [])
    ))
    configured_required = dict(configured.get('required_columns') or {})
    settings['required_columns'] = {
        'all_files': list(dict.fromkeys(defaults['required_columns']['all_files'] + list(configured_required.get('all_files') or []))),
        'by_view': {**defaults['required_columns']['by_view'], **dict(configured_required.get('by_view') or {})},
    }
    dictionary = dict(settings['dictionary'])
    dictionary_views = all_als_preflight.load_dictionary(
        options['data_dict_path'],
        view_column=dictionary.get('view_column', 'View Name'),
        field_column=dictionary.get('field_column', 'Field'),
        description_column=dictionary.get('description_column', 'Description'),
        value_column=dictionary.get('value_column', 'Values'),
        definition_value_markers=dictionary.get('definition_value_markers', ['', 'NA']),
    )
    aliases = all_als_match_manifest.resolve_aliases(settings.get('view_aliases'), dictionary_views)
    preflight_groups = {
        source_id: aliases.get(all_als_preflight.normalize(view_name), view_name)
        for source_id, view_name in groups.items()
    }
    options['_all_als_view_aliases'] = aliases
    policy = settings.get('phi_pii_columns_file') or options.get('phi_pii_columns_file')
    if not policy:
        raise ValueError('ALL ALS update requires phi_pii_columns_file configuration')
    settings.update(dictionary)
    settings['phi_pii_columns_file'] = policy
    date_policy = settings.get('date_screening_policy_file')
    if not date_policy:
        date_policy = str(_DEFAULT_DATE_POLICY)
    settings['date_screening_policy_file'] = date_policy
    settings['preflight_report'] = options.get('preflight_report') or settings.get('preflight_report')
    settings['include_violation_values'] = bool(
        options.get('include_violation_values') or settings.get('include_violation_values')
    )
    settings['dictionary_views'] = dictionary_views
    preflight_warnings = all_als_preflight.validate(staging, paths, preflight_groups, settings)
    warnings = [warning for view in dictionary_views.values() for warning in view.get('warnings', [])]
    warnings.extend(preflight_warnings)
    for warning in warnings:
        print(f'⚠️  ALL ALS dictionary warning: {warning}')
    print(f'✓ ALL ALS preflight passed: {len(staging)} staged file(s), {len(dictionary_views)} dictionary view(s)')
    return names, paths, groups, {}


def match(existing, staging, names, groups, targets, services):
    forms = {}
    for sid, name in names.items():
        forms.setdefault(services._norm_filename_for_match(name), []).append((sid, name))
    matches, claimed = {}, set()
    for target, data in existing.items():
        filename, annotations = next(iter(data.items()))
        view = annotations.get('viewName')
        if isinstance(view, list):
            view = view[0] if view else None
        candidates = [sid for sid, _ in forms.get(services._norm_filename_for_match(filename), []) if sid not in claimed]
        if len(candidates) > 1:
            candidates = ([sid for sid in candidates if groups.get(sid, '').lower() == view.lower()]
                          if view else candidates)
            if len(candidates) != 1:
                raise ValueError(f'Ambiguous ALL ALS form match for {filename}')
        source = candidates[0] if candidates else None
        # A canonical ALL ALS view is a deterministic identity and must win over
        # similarity matching; forms such as "Eligibility Criteria 2" are distinct.
        if not source and view:
            candidates = [sid for sid, group in groups.items() if group.lower() == view.lower() and sid not in claimed]
            if len(candidates) > 1:
                raise ValueError(f'Ambiguous ALL ALS view match for {view}')
            source = candidates[0] if candidates else None
        # Never use fuzzy matching to override or guess a view-identified ALL ALS
        # form. Similar titles (for example, "Eligibility Criteria" vs "... 2")
        # are separate forms; leave an unresolved view for review instead.
        if not source and not view:
            fuzzy = services._fuzzy_match_filename(filename, forms, exclude_ids=claimed)
            source = fuzzy[0] if fuzzy else None
        if not source and target in staging and target not in claimed:
            source = target
        if source:
            matches[target] = source
            claimed.add(source)
    return matches
