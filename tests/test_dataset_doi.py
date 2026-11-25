import json
from types import SimpleNamespace

import pytest

from synapse_dataset_manager import cli
from synapse_dataset_manager.dataset_doi import dataset_doi_request, preview_dataset_doi, mint_dataset_doi


class Missing(Exception):
    def __init__(self, code=404):
        self.response = SimpleNamespace(status_code=code)


class Syn:
    def __init__(self, version=None):
        self.version = version
        self.posts = []
        self.association_exists = False
        self.report_path = None

    def restGET(self, path, **kwargs):
        assert kwargs['retryPolicy'] == {'retries': 0}
        if path.startswith('/entity/'):
            return {'id': 'syn123', 'versionNumber': self.version,
                    'concreteType': 'org.sagebionetworks.repo.model.table.Dataset'}
        if path.startswith('/doi/async/get/'):
            assert json.loads(self.report_path.read_text())['start_response']['token'] == '123'
            return {'doi': {'associationId': '42', 'objectId': 'syn123', 'objectType': 'ENTITY',
                            'objectVersion': self.version}}
        if not self.association_exists:
            raise Missing()
        return {'associationId': '42', 'objectId': 'syn123', 'objectType': 'ENTITY',
                'objectVersion': self.version, 'doiUri': '10.7303/syn123'}

    def restPOST(self, path, **kwargs):
        assert json.loads(self.report_path.read_text())['status'] == 'submission_outcome_unknown'
        self.posts.append((path, kwargs))
        self.association_exists = True
        return {'token': '123'}


def request(version=None):
    return dataset_doi_request('syn123', version, ['A, B'], 'Title', 2025)


@pytest.mark.parametrize('version', [None, 4])
def test_success_single_post_and_durable_token(tmp_path, version):
    syn = Syn(version)
    syn.report_path = tmp_path / 'report.json'
    result = mint_dataset_doi(syn, request(version), str(syn.report_path), 3)
    assert result['status'] == 'completed'
    assert len(syn.posts) == 1
    assert syn.posts[0][1]['retryPolicy'] == {'retries': 0}
    assert json.loads(syn.report_path.read_text()) == result


def test_existing_and_authorization_fail_closed(tmp_path):
    syn = Syn()
    syn.association_exists = True
    with pytest.raises(ValueError, match='already exists'):
        mint_dataset_doi(syn, request(), str(tmp_path / 'one'), 3)
    assert not syn.posts
    syn.restGET = lambda *a, **k: (_ for _ in ()).throw(Missing(403))
    with pytest.raises(Missing):
        preview_dataset_doi(syn, request())


def test_unknown_post_outcome_never_retries(tmp_path):
    syn = Syn()
    syn.report_path = tmp_path / 'report'
    def fail(*args, **kwargs):
        syn.posts.append(args)
        raise TimeoutError()
    syn.restPOST = fail
    with pytest.raises(TimeoutError):
        mint_dataset_doi(syn, request(), str(syn.report_path), 3)
    assert len(syn.posts) == 1
    assert json.loads(syn.report_path.read_text())['status'] == 'submission_outcome_unknown'
    with pytest.raises(FileExistsError):
        mint_dataset_doi(syn, request(), str(syn.report_path), 3)
    assert len(syn.posts) == 1


def test_association_mismatch_fails_closed(tmp_path):
    syn = Syn()
    syn.report_path = tmp_path / 'report'
    original = syn.restGET
    def get(path, **kwargs):
        value = original(path, **kwargs)
        if path.startswith('/doi/association'):
            value['objectId'] = 'syn999'
        return value
    syn.restGET = get
    with pytest.raises(ValueError, match='mismatch'):
        mint_dataset_doi(syn, request(), str(syn.report_path), 3)
    assert json.loads(syn.report_path.read_text())['status'] == 'verification_pending'


@pytest.mark.parametrize('version', [0, -1, True])
def test_invalid_version_rejected(version):
    with pytest.raises(ValueError):
        request(version)


def test_cli_requires_all_acknowledgements_before_login(monkeypatch, tmp_path):
    monkeypatch.setattr(cli.synapseclient, 'Synapse', lambda: pytest.fail('must not log in'))
    args = SimpleNamespace(dataset_id='syn123', version=None, creator=['A'], title='T', year=2025,
                           execute=True, output=str(tmp_path / 'report'), confirm='syn123:latest',
                           coordinate=False, acknowledge_production=True, poll_timeout=120)
    with pytest.raises(ValueError, match='requires'):
        cli.handle_mint_dataset_doi(args, None)


def test_missing_token_leaves_unknown_report(tmp_path):
    syn = Syn()
    syn.report_path = tmp_path / 'report'
    syn.restPOST = lambda *a, **kw: {}
    with pytest.raises(ValueError, match='do not resubmit'):
        mint_dataset_doi(syn, request(), str(syn.report_path), 3)
    assert json.loads(syn.report_path.read_text())['status'] == 'submission_outcome_unknown'


def test_poll_timeout_leaves_token_and_does_not_resubmit(tmp_path, monkeypatch):
    from synapse_dataset_manager import dataset_doi
    syn = Syn()
    syn.report_path = tmp_path / 'report'
    original = syn.restGET
    def get(path, **kwargs):
        if path.startswith('/doi/async/get/'):
            return {'jobState': 'PROCESSING'}
        return original(path, **kwargs)
    syn.restGET = get
    clock = iter([0, 0, 1, 1, 2])
    monkeypatch.setattr(dataset_doi.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(dataset_doi.time, 'sleep', lambda _: None)
    with pytest.raises(TimeoutError, match='never resubmit'):
        mint_dataset_doi(syn, request(), str(syn.report_path), 1)
    assert len(syn.posts) == 1
    assert json.loads(syn.report_path.read_text())['start_response']['token'] == '123'


def test_bad_poll_result_fails_closed(tmp_path):
    syn = Syn()
    syn.report_path = tmp_path / 'report'
    original = syn.restGET
    syn.restGET = lambda path, **kw: ({'jobState': 'FAILED'} if path.startswith('/doi/async/get/')
                                      else original(path, **kw))
    with pytest.raises(ValueError, match='failed or returned'):
        mint_dataset_doi(syn, request(), str(syn.report_path), 3)
    assert len(syn.posts) == 1


def test_preview_version_query_and_no_post():
    syn = Syn(4)
    original = syn.restGET
    paths = []
    def get(path, **kwargs):
        paths.append(path)
        return original(path, **kwargs)
    syn.restGET = get
    preview_dataset_doi(syn, request(4))
    assert paths == ['/entity/syn123/version/4', '/doi/association?id=syn123&type=ENTITY&version=4']
    assert not syn.posts


def test_successful_rebuild_only_recommends_separate_doi(monkeypatch, tmp_path, capsys):
    from synapse_dataset_manager import dataset_rebuild
    manifest = tmp_path / 'manifest'
    manifest.write_text(json.dumps({'source_dataset_id': 'syn1', 'source_baseline': {}}))
    syn = SimpleNamespace(login=lambda **kwargs: None)
    monkeypatch.setattr(cli.synapseclient, 'Synapse', lambda: syn)
    monkeypatch.setattr(cli, 'plan_dataset_rebuild', lambda *args: {})
    monkeypatch.setattr(cli, '_dataset_snapshot_baseline', lambda *args: {})
    monkeypatch.setattr(dataset_rebuild, 'execute_dataset_rebuild', lambda *args: {'status': 'completed'})
    monkeypatch.setattr(cli, 'handle_mint_dataset_doi', lambda *args: pytest.fail('must not mint'))
    args = SimpleNamespace(execute=True, output=str(tmp_path / 'out'), manifest=str(manifest))
    assert cli.handle_rebuild_dataset_entity(args, None)['status'] == 'completed'
    assert 'mint-dataset-doi separately; no DOI was minted' in capsys.readouterr().out
