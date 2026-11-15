import os
import re

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from moto import mock_aws

# Configure test environment
os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://mirr:mirrpassword@localhost:5432/mirr?sslmode=disable')
os.environ['R2_ENDPOINT'] = 'mock://r2'
os.environ['R2_BUCKET'] = 'music-info-retrieval-research-1'
os.environ['R2_ACCESS_KEY_ID'] = 'fake-access-key'
os.environ['R2_SECRET_ACCESS_KEY'] = 'fake-secret-key'
os.environ['R2_PUBLIC_BASE_URL'] = 'https://pub-fake.r2.dev'
os.environ['CELERY_EAGER'] = '1'
os.environ['ALLOW_PLACEHOLDER_STEMS'] = '1'

from backend.app.main import app
from backend.app.auth import get_current_user_id
import db.engine as db_engine
from db import store as db_store
import services.storage as storage_module
from shared.schemas import StageStatus

# Override user_id for test suite
TEST_USER_ID = 'test-user-1234'
app.dependency_overrides[get_current_user_id] = lambda: TEST_USER_ID

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_mock_s3():
    with mock_aws():
        s3 = storage_module.get_s3_client()
        s3.create_bucket(Bucket=os.environ['R2_BUCKET'])
        yield s3


def test_missing_database_url_raises(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    with pytest.raises(RuntimeError, match='DATABASE_URL environment variable is required'):
        db_engine.get_database_url()


def test_sqlite_database_url_raises(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///local.db')
    with pytest.raises(RuntimeError, match='SQLite is not supported'):
        db_engine.get_database_url()


def test_missing_r2_settings_raises(monkeypatch):
    monkeypatch.delenv('R2_ENDPOINT', raising=False)
    with pytest.raises(RuntimeError, match='Missing required Cloudflare R2 environment variables'):
        storage_module.get_r2_settings()


def test_health_endpoint():
    response = client.get('/health')
    assert response.status_code in (200, 503)
    data = response.json()
    assert 'database' in data
    assert 'redis' in data
    assert 'storage' in data
    assert 'worker' in data


def test_presigned_upload_flow():
    res = client.post(
        '/api/v1/uploads/presign',
        json={
            'filename': 'test.wav',
            'content_type': 'audio/wav',
            'size_bytes': 1024,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert 'file_id' in data
    assert 'upload_url' in data
    assert data['object_key'].startswith('uploads/')


def test_presigned_upload_invalid_type():
    res = client.post(
        '/api/v1/uploads/presign',
        json={
            'filename': 'test.txt',
            'content_type': 'text/plain',
            'size_bytes': 1024,
        },
    )
    assert res.status_code == 415


def test_complete_upload_and_session_access():
    file_id = 'test-file-abc'
    object_key = f'uploads/{file_id}/test.wav'
    # Put object in mock S3 first
    s3 = storage_module.get_s3_client()
    s3.put_object(Bucket=os.environ['R2_BUCKET'], Key=object_key, Body=b'RIFFdemo', ContentType='audio/wav')

    res = client.post(
        '/api/v1/uploads/complete',
        json={
            'file_id': file_id,
            'object_key': object_key,
            'filename': 'test.wav',
            'content_type': 'audio/wav',
            'size_bytes': 8,
        },
    )
    assert res.status_code == 200

    # Retrieve session
    sess_res = client.get(f'/api/v1/session/{file_id}')
    assert sess_res.status_code == 200
    sess = sess_res.json()
    assert sess['file_id'] == file_id
    assert sess['user_id'] == TEST_USER_ID

    # Test deprecated alias
    legacy_res = client.get(f'/api/session/{file_id}')
    assert legacy_res.status_code == 200


@pytest.mark.parametrize(('content_type', 'max_mb', 'expected_status'), [
    ('audio/wav', 0, 413),
    ('text/plain', 1, 415),
])
def test_complete_upload_rejects_and_deletes_invalid_object(monkeypatch, setup_mock_s3, content_type, max_mb, expected_status):
    from backend.app import main

    monkeypatch.setattr(main, 'MAX_UPLOAD_MB', max_mb)
    object_key = 'uploads/test-invalid/source.wav'
    setup_mock_s3.put_object(Bucket=os.environ['R2_BUCKET'], Key=object_key, Body=b'data', ContentType=content_type)
    res = client.post('/api/v1/uploads/complete', json={
        'file_id': 'test-invalid', 'object_key': object_key, 'filename': 'source.wav',
        'content_type': 'audio/wav', 'size_bytes': 1,
    })
    assert res.status_code == expected_status
    assert setup_mock_s3.list_objects_v2(Bucket=os.environ['R2_BUCKET'], Prefix=object_key).get('KeyCount') == 0


def test_complete_upload_uses_stored_metadata(monkeypatch, setup_mock_s3):
    from backend.app import main

    object_key = 'uploads/test-metadata/source.wav'
    setup_mock_s3.put_object(Bucket=os.environ['R2_BUCKET'], Key=object_key, Body=b'data', ContentType='audio/wav')
    sessions, artifacts, tasks = [], [], []
    monkeypatch.setattr(main.db_store, 'save_session', sessions.append)
    monkeypatch.setattr(main.db_store, 'save_artifact', artifacts.append)
    monkeypatch.setattr(main.analyze_audio_task, 'delay', lambda *args: tasks.append(args))
    res = client.post('/api/v1/uploads/complete', json={
        'file_id': 'test-metadata', 'object_key': object_key, 'filename': 'source.wav',
        'content_type': 'audio/mpeg', 'size_bytes': 1,
    })
    assert res.status_code == 200
    assert sessions[0]['size'] == artifacts[0]['size'] == 4
    assert sessions[0]['content_type'] == artifacts[0]['mime_type'] == 'audio/wav'
    assert len(tasks) == 1


def test_session_ownership_enforcement():
    # Save a session belonging to another user
    other_file_id = 'other-user-session'
    db_store.save_session({
        'file_id': other_file_id,
        'user_id': 'someone-else',
        'filename': 'other.wav',
    })
    res = client.get(f'/api/v1/session/{other_file_id}')
    assert res.status_code == 403


def test_multipart_upload_and_separation_flow():
    wav_bytes = b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00'
    res = client.post(
        '/api/v1/upload',
        files={'file': ('sample.wav', wav_bytes, 'audio/wav')},
    )
    assert res.status_code == 200
    file_id = res.json()['file_id']

    # Trigger separation
    sep_res = client.post('/api/v1/separate', json={'file_id': file_id})
    assert sep_res.status_code == 200

    # Check session
    sess = client.get(f'/api/v1/session/{file_id}').json()
    assert sess['stems'] is not None
    assert sess['stems']['status'] == 'completed'
    assert len(sess['stems']['stems']) == 4

def test_complete_upload_security_ownership_and_replay(setup_mock_s3):
    # Presign an upload for user A
    presign_res = client.post(
        '/api/v1/uploads/presign',
        json={'filename': 'song.wav', 'content_type': 'audio/wav', 'size_bytes': 1024},
    )
    assert presign_res.status_code == 200
    pdata = presign_res.json()
    file_id = pdata['file_id']
    object_key = pdata['object_key']

    setup_mock_s3.put_object(Bucket=os.environ['R2_BUCKET'], Key=object_key, Body=b'data1234', ContentType='audio/wav')

    # Try completing as another user
    app.dependency_overrides[get_current_user_id] = lambda: 'other-hacker'
    res_hijack = client.post(
        '/api/v1/uploads/complete',
        json={'file_id': file_id, 'object_key': object_key, 'filename': 'song.wav', 'content_type': 'audio/wav', 'size_bytes': 8},
    )
    assert res_hijack.status_code == 403

    # Complete as owner
    app.dependency_overrides[get_current_user_id] = lambda: TEST_USER_ID
    res_ok = client.post(
        '/api/v1/uploads/complete',
        json={'file_id': file_id, 'object_key': object_key, 'filename': 'song.wav', 'content_type': 'audio/wav', 'size_bytes': 8},
    )
    assert res_ok.status_code == 200

    # Try replay complete
    res_replay = client.post(
        '/api/v1/uploads/complete',
        json={'file_id': file_id, 'object_key': object_key, 'filename': 'song.wav', 'content_type': 'audio/wav', 'size_bytes': 8},
    )
    assert res_replay.status_code == 409


def test_ssl_default_local_vs_remote():
    from db.engine import create_engine_for_url
    import inspect

    e_local = create_engine_for_url('postgresql+psycopg://u:p@localhost:5432/db')
    cparams_local = inspect.getclosurevars(e_local.pool._creator).nonlocals['cparams']
    assert cparams_local['sslmode'] == 'disable'

    e_remote = create_engine_for_url('postgresql+psycopg://u:p@aws-0-eu-west-3.pooler.supabase.com:5432/postgres')
    cparams_remote = inspect.getclosurevars(e_remote.pool._creator).nonlocals['cparams']
    assert cparams_remote['sslmode'] == 'require'


PUBLIC_API_PATHS = {'/health'}
PUBLIC_DOC_PATHS = {'/docs', '/redoc', '/openapi.json'}
WAV_BYTES = b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00'


def _depends_on(dependant, call) -> bool:
    return any(dep.call is call or _depends_on(dep, call) for dep in dependant.dependencies)


def _api_routes() -> list[APIRoute]:
    return [route for route in app.routes if isinstance(route, APIRoute)]


PROTECTED_ROUTES = [
    (method, route.path)
    for route in _api_routes()
    if route.path not in PUBLIC_API_PATHS
    for method in sorted(route.methods)
]
V1_ROUTES = [route for route in _api_routes() if route.path.startswith('/api/v1/')]


@pytest.fixture
def real_auth():
    """Run the real get_current_user_id instead of the suite-wide override."""
    override = app.dependency_overrides.pop(get_current_user_id)
    try:
        yield
    finally:
        app.dependency_overrides[get_current_user_id] = override


@pytest.fixture
def as_user():
    def _set(user_id):
        app.dependency_overrides[get_current_user_id] = lambda: user_id
    yield _set
    app.dependency_overrides[get_current_user_id] = lambda: TEST_USER_ID


def test_only_allowlisted_routes_are_public():
    public_api = {route.path for route in _api_routes() if not _depends_on(route.dependant, get_current_user_id)}
    assert public_api == PUBLIC_API_PATHS
    other_paths = {route.path for route in app.routes if not isinstance(route, APIRoute)}
    assert other_paths == PUBLIC_DOC_PATHS


def test_legacy_aliases_are_registered_and_protected():
    legacy = {route.path for route in _api_routes() if route.path.startswith('/api/') and not route.path.startswith('/api/v1/')}
    assert legacy == {'/api/upload', '/api/session/{file_id}', '/api/analyze', '/api/separate'}
    assert {p for _, p in PROTECTED_ROUTES} >= legacy


@pytest.mark.parametrize(('method', 'path'), PROTECTED_ROUTES)
@pytest.mark.parametrize('headers', [{}, {'Authorization': 'Bearer not-a-jwt'}], ids=['no-token', 'bad-token'])
def test_protected_routes_reject_missing_or_invalid_token(real_auth, method, path, headers):
    url = re.sub(r'\{[^}]+\}', 'some-id', path)
    res = client.request(method, url, headers=headers)
    assert res.status_code == 401
    assert res.headers.get('www-authenticate') == 'Bearer'


@pytest.mark.parametrize('path', sorted(PUBLIC_DOC_PATHS))
def test_docs_are_public(real_auth, path):
    assert client.get(path).status_code == 200


def test_oauth2_redirect_route_is_disabled():
    assert client.get('/docs/oauth2-redirect').status_code == 404


@pytest.mark.parametrize('prefix', ['/api/v1', '/api'])
@pytest.mark.parametrize(('method', 'path_template'), [
    ('GET', '{prefix}/session/{file_id}'),
    ('POST', '{prefix}/analyze'),
    ('POST', '{prefix}/separate'),
])
def test_session_routes_enforce_ownership(prefix, method, path_template):
    file_id = f'owned-by-other{prefix.replace("/", "-")}'
    db_store.save_session({
        'file_id': file_id,
        'user_id': 'someone-else',
        'filename': 'other.wav',
        'artifact_url': 'https://pub-fake.r2.dev/uploads/x/other.wav',
    })
    path = path_template.format(prefix=prefix, file_id=file_id)
    res = client.request(method, path, json={'file_id': file_id} if method == 'POST' else None)
    assert res.status_code == 403


@pytest.mark.parametrize('prefix', ['/api/v1', '/api'])
def test_upload_binds_session_to_caller(prefix, as_user):
    res = client.post(f'{prefix}/upload', files={'file': ('sample.wav', WAV_BYTES, 'audio/wav')})
    assert res.status_code == 200
    file_id = res.json()['file_id']
    assert db_store.get_session(file_id)['user_id'] == TEST_USER_ID

    as_user('intruder')
    assert client.get(f'{prefix}/session/{file_id}').status_code == 403
    assert client.post(f'{prefix}/separate', json={'file_id': file_id}).status_code == 403


@pytest.mark.parametrize('prefix', ['/api/v1', '/api'])
def test_upload_rejects_unsupported_type_with_415(prefix):
    res = client.post(f'{prefix}/upload', files={'file': ('notes.txt', b'hello', 'text/plain')})
    assert res.status_code == 415
    assert res.json()['error_code'] == 'upload_invalid_type'


def test_v1_routes_have_stable_operation_ids_and_response_models():
    operation_ids = [route.operation_id for route in V1_ROUTES]
    assert sorted(operation_ids) == sorted([
        'presignUpload', 'completeUpload', 'uploadFile', 'getSession', 'analyzeAudio', 'separateStems',
    ])
    assert all(route.response_model is not None for route in V1_ROUTES)


def test_v1_routes_document_error_responses():
    spec = client.get('/openapi.json').json()
    expected = {
        ('post', '/api/v1/uploads/presign'): {'401', '413', '415', '422'},
        ('post', '/api/v1/uploads/complete'): {'400', '401', '403', '404', '409', '413', '415', '422'},
        ('post', '/api/v1/upload'): {'400', '401', '413', '415', '422'},
        ('get', '/api/v1/session/{file_id}'): {'401', '403', '404', '422'},
        ('post', '/api/v1/analyze'): {'400', '401', '403', '404', '422'},
        ('post', '/api/v1/separate'): {'400', '401', '403', '404', '422'},
    }
    v1_ops = {(m, p) for p, ops in spec['paths'].items() if p.startswith('/api/v1/') for m in ops}
    assert v1_ops == set(expected)
    for (method, path), codes in expected.items():
        responses = spec['paths'][path][method]['responses']
        assert set(responses) - {'200'} == codes, path
        assert all('content' in responses[c] for c in codes), path


def test_stage_status_is_documented_enum():
    schemas = client.get('/openapi.json').json()['components']['schemas']
    assert schemas['StageStatus']['enum'] == [s.value for s in StageStatus] == ['pending', 'active', 'completed', 'failed']
    for name in ('WorkflowStageStatus', 'AnalysisMetadata', 'StemsMetadata'):
        assert schemas[name]['properties']['status'] == {'$ref': '#/components/schemas/StageStatus'}


def test_session_response_preserves_stored_fields():
    file_id = 'session-shape'
    db_store.save_session({
        'file_id': file_id,
        'user_id': TEST_USER_ID,
        'filename': 'a.wav',
        'analysis': {'file_id': file_id, 'status': 'completed', 'bpm': 120.0},
        'stems': {'file_id': file_id, 'status': 'completed', 'stems': [
            {'name': 'drums', 'filename': 'drums.wav', 'url': 'https://x/drums.wav', 'key': 'stems/s/drums.wav',
             'storage_backend': 'r2', 'size': 1, 'format': 'wav', 'mime_type': 'audio/wav'},
        ]},
        'workflow_stages': [{'stage': 'upload', 'status': 'completed', 'message': 'ok'}],
    })
    body = client.get(f'/api/v1/session/{file_id}').json()
    assert body['analysis'] == {
        'file_id': file_id, 'status': 'completed', 'bpm': 120.0, 'key': None, 'structure': None, 'duration': None,
        'waveform_url': None, 'task_id': None, 'message': None, 'next_action': None, 'analyzed_at': None,
    }
    assert body['stems']['stems'][0]['key'] == 'stems/s/drums.wav'
    assert body['stems']['stems'][0]['filename'] == 'drums.wav'
    assert set(body) == {
        'file_id', 'user_id', 'filename', 'content_type', 'size', 'artifact_url', 'analysis', 'stems',
        'workflow_stages', 'created_at', 'updated_at',
    }
