import os
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

# Configure test environment
os.environ['DATABASE_URL'] = 'postgresql+psycopg://mirr:mirr@localhost:5432/mirr'
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
    assert res.status_code == 400


def test_complete_upload_and_session_access():
    file_id = 'test-file-abc'
    object_key = f'uploads/{file_id}/test.wav'
    # Put object in mock S3 first
    s3 = storage_module.get_s3_client()
    s3.put_object(Bucket=os.environ['R2_BUCKET'], Key=object_key, Body=b'RIFFdemo')

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
