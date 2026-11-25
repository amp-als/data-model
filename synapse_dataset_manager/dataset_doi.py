"""Preview and submit a single, explicitly coordinated Dataset DOI request."""
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from urllib.parse import quote, urlencode


def dataset_doi_request(dataset_id, version, creators, title, year):
    if not isinstance(dataset_id, str) or not re.fullmatch(r'syn[1-9][0-9]*', dataset_id):
        raise ValueError('Dataset ID must be a Synapse ID')
    if version is not None and (not isinstance(version, int) or isinstance(version, bool) or version < 1):
        raise ValueError('Dataset snapshot version must be a positive integer')
    if (not isinstance(creators, list) or not creators or
            any(not isinstance(c, str) or not c.strip() for c in creators)):
        raise ValueError('At least one nonempty creator is required')
    if not isinstance(title, str) or not title.strip():
        raise ValueError('A nonempty DOI title is required')
    if (not isinstance(year, int) or isinstance(year, bool) or
            not 1000 <= year <= datetime.now(timezone.utc).year + 1):
        raise ValueError('Publication year must be between 1000 and next year')
    return {'concreteType': 'org.sagebionetworks.repo.model.doi.v2.DoiRequest',
            'doi': {'objectId': dataset_id, 'objectType': 'ENTITY', 'objectVersion': version,
                    'creators': [{'creatorName': c.strip()} for c in creators],
                    'titles': [{'title': title.strip()}], 'publicationYear': year,
                    'resourceType': {'resourceTypeGeneral': 'Dataset'}}}


def _association_path(doi):
    params = {'id': doi['objectId'], 'type': 'ENTITY'}
    if doi['objectVersion'] is not None:
        params['version'] = doi['objectVersion']
    return '/doi/association?' + urlencode(params)


def _get(syn, path, timeout=30):
    return syn.restGET(path, retryPolicy={'retries': 0}, timeout=timeout)


def preview_dataset_doi(syn, request):
    doi = request['doi']
    path = '/entity/' + doi['objectId']
    if doi['objectVersion'] is not None:
        path += '/version/' + str(doi['objectVersion'])
    entity = _get(syn, path)
    if (not isinstance(entity, dict) or
            entity.get('concreteType') != 'org.sagebionetworks.repo.model.table.Dataset' or
            entity.get('id') != doi['objectId'] or
            (doi['objectVersion'] is not None and entity.get('versionNumber') != doi['objectVersion'])):
        raise ValueError('Requested Dataset and snapshot could not be verified')
    try:
        association = _get(syn, _association_path(doi))
    except Exception as error:
        response = getattr(error, 'response', None)
        if response is not None and response.status_code == 404:
            return request
        raise
    raise ValueError(f'DOI association already exists or response is ambiguous: {association!r}')


def _sync_dir(path):
    fd = os.open(os.path.dirname(os.path.abspath(path)), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _save_report(path, report, exclusive=False):
    data = (json.dumps(report, indent=2) + '\n').encode()
    if exclusive:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        temp = None
    else:
        fd, temp = tempfile.mkstemp(prefix='.doi-report-', dir=os.path.dirname(os.path.abspath(path)))
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if temp:
            os.replace(temp, path)
        _sync_dir(path)
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)


def mint_dataset_doi(syn, request, output, poll_timeout):
    if not isinstance(poll_timeout, int) or isinstance(poll_timeout, bool) or not 1 <= poll_timeout <= 3600:
        raise ValueError('Poll timeout must be between 1 and 3600 seconds')
    # Reserve the recovery artifact before preflight, and persist the uncertainty before POST.
    report = {'status': 'preflight', 'request': request}
    _save_report(output, report, exclusive=True)
    preview_dataset_doi(syn, request)
    report['status'] = 'submission_outcome_unknown'
    _save_report(output, report)
    started = syn.restPOST('/doi/async/start', body=json.dumps(request),
                           retryPolicy={'retries': 0}, timeout=30)
    token = started.get('token') if isinstance(started, dict) else None
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', token):
        raise ValueError('Submission outcome unknown: response did not contain a valid token; do not resubmit')
    report.update(status='submitted', start_response=started)
    _save_report(output, report)
    deadline = time.monotonic() + poll_timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('DOI polling timed out; use the saved token to investigate, never resubmit automatically')
        result = _get(syn, '/doi/async/get/' + quote(token, safe=''), timeout=min(30, remaining))
        if not isinstance(result, dict):
            raise ValueError('Malformed DOI polling response; investigate saved token')
        if result.get('jobState') == 'PROCESSING':
            time.sleep(min(1, max(0, deadline - time.monotonic())))
            continue
        if result.get('jobState') not in (None, 'COMPLETE') or not isinstance(result.get('doi'), dict):
            raise ValueError('DOI job failed or returned an ambiguous response; investigate saved token')
        break
    report['result'] = result
    report['status'] = 'verification_pending'
    _save_report(output, report)
    association = _get(syn, _association_path(request['doi']))
    expected = request['doi']
    returned = result['doi']
    for obj in (returned, association):
        if (not isinstance(obj, dict) or obj.get('objectId') != expected['objectId'] or
                obj.get('objectType') != 'ENTITY' or obj.get('objectVersion') != expected['objectVersion']):
            raise ValueError('DOI response or association target mismatch; investigate saved token')
    if (not returned.get('associationId') or returned.get('associationId') != association.get('associationId') or
            not isinstance(association.get('doiUri'), str) or
            not re.fullmatch(r'10\.\d{4,9}/\S+', association['doiUri'])):
        raise ValueError('DOI association ID or URI invalid; investigate saved token')
    report.update(status='completed', association=association)
    _save_report(output, report)
    return report
