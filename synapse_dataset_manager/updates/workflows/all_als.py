"""Explicit ALL ALS form/view identity policy and mandatory header preflight."""

from synapse_dataset_manager.updates import all_als_preflight


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
            'ignored_file_columns': ['Form Name', 'NeuroGUID'],
        },
        'required_columns': {
            'all_files': ['NeuroGUID', 'NeuroSTAmP'],
            'by_view': {'v_ALLALS_AS_DEMOGRAPHICS': ['nihguid']},
        },
    }
    configured = dict(options.get('all_als') or {})
    settings = {**defaults, **configured}
    settings['dictionary'] = {**defaults['dictionary'], **dict(configured.get('dictionary') or {})}
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
    )
    policy = settings.get('phi_pii_columns_file') or options.get('phi_pii_columns_file')
    if not policy:
        raise ValueError('ALL ALS update requires phi_pii_columns_file configuration')
    settings.update(dictionary)
    settings['phi_pii_columns_file'] = policy
    settings['dictionary_views'] = dictionary_views
    all_als_preflight.validate(staging, paths, groups, settings)
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
        if not source:
            fuzzy = services._fuzzy_match_filename(filename, forms, exclude_ids=claimed)
            source = fuzzy[0] if fuzzy else None
        if not source and view:
            candidates = [sid for sid, group in groups.items() if group.lower() == view.lower() and sid not in claimed]
            if len(candidates) > 1:
                raise ValueError(f'Ambiguous ALL ALS view match for {view}')
            source = candidates[0] if candidates else None
        if not source and target in staging and target not in claimed:
            source = target
        if source:
            matches[target] = source
            claimed.add(source)
    return matches
