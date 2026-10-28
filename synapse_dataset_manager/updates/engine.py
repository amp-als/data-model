"""Plan review, preflight, fail-fast execution, and durable result reporting."""

import json
import os
from pathlib import Path
import tempfile

from .plans import assert_current, build_plan, load_plan, write_plan


def _save_report(path, report):
    # Replace atomically so interrupted writes do not corrupt the last checkpoint.
    with tempfile.NamedTemporaryFile(mode='w', dir=Path(path).parent, delete=False) as stream:
        temporary = stream.name
        try:
            json.dump(report, stream, indent=2)
            stream.write('\n')
        except BaseException:
            os.unlink(temporary)
            raise
    os.replace(temporary, path)


def run_update(backend, dataset_id, workflow, annotations, options, *, dry_run,
               plan_file=None, write_plan_file=None):
    if plan_file and write_plan_file:
        raise ValueError('Choose --plan-file or --write-plan, not both')
    if not dry_run and (not plan_file or write_plan_file):
        raise ValueError('--execute requires a reviewed --plan-file; first run a dry run to write a plan')
    reviewed = load_plan(plan_file) if plan_file else None
    current = build_plan(backend, dataset_id, workflow, annotations, options)
    if reviewed is not None:
        assert_current(reviewed, current)
    if dry_run:
        if reviewed is None:
            if not write_plan_file:
                raise ValueError('A plan output path is required')
            write_plan(write_plan_file, current)
            print(f'Review plan: {write_plan_file}')
        for action in current['actions']:
            print(f"  [DRY_RUN] {action['kind']}: {action['target_id']} ({action['filename']})")
        return {'status': 'dry_run', 'plan_id': current['plan_id'], 'actions': current['actions']}

    report_path = str(plan_file) + '.results.json'
    # A plan cannot silently be replayed after an interrupted/partial attempt.
    if Path(report_path).exists():
        raise ValueError(f'Execution report already exists: {report_path}; inspect it and generate a fresh plan')
    with tempfile.TemporaryDirectory(prefix='sdm_apply_') as directory:
        paths = backend.prepare_content(reviewed, directory)
        # Downloads/copies can take time. Recheck everything before the first write.
        assert_current(reviewed, build_plan(backend, dataset_id, workflow, annotations, options))
        report = {'plan_id': reviewed['plan_id'], 'status': 'in_progress',
                  'actions': [{**action, 'status': 'not_started'} for action in reviewed['actions']]}
        with open(report_path, 'x') as stream:
            json.dump(report, stream, indent=2)
        try:
            for action, result in zip(reviewed['actions'], report['actions']):
                # Detect per-file changes since the full preflight. This is not a
                # distributed transaction; the server may still race a subsequent write.
                for entity_id in (action['target_id'], action.get('source_id')):
                    if entity_id and backend.snapshot(entity_id) != reviewed['snapshots'][entity_id]:
                        raise ValueError(f'Stale entity immediately before action: {entity_id}')
                result['status'] = 'applying'
                _save_report(report_path, report)
                backend.apply(reviewed, action, annotations, paths)
                result['status'] = 'verifying'
                _save_report(report_path, report)
                verification_state = backend.snapshot(action['target_id'])
                failures = backend.verify(reviewed, action, annotations)
                if failures:
                    result['verification_failures'] = failures
                    raise RuntimeError('; '.join(failures))
                result['observed_state'] = backend.snapshot(action['target_id'])
                if result['observed_state'] != verification_state:
                    raise RuntimeError(f'Entity changed during verification: {action["target_id"]}')
                result['status'] = 'verified'
                _save_report(report_path, report)
            observed = {result['target_id']: result['observed_state'] for result in report['actions']}
            for entity_id, state in observed.items():
                if backend.snapshot(entity_id) != state:
                    raise RuntimeError(f'Entity changed after verification: {entity_id}')
            failures = backend.verify_dataset(reviewed, observed)
            if failures:
                report['verification_failures'] = failures
                raise RuntimeError('; '.join(failures))
            report['status'] = 'complete'
        except BaseException as error:
            report['status'] = 'incomplete'
            report['error'] = str(error) or type(error).__name__
            if 'result' in locals() and result['status'] != 'verified':
                result['status'] = 'failed_or_partial'
            _save_report(report_path, report)
            raise RuntimeError(f'Update incomplete; inspect {report_path}: {error}') from error
        _save_report(report_path, report)
    print(f'Update verified. Execution report: {report_path}')
    return report
