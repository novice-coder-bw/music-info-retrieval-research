import io
from pathlib import Path
import main
from fastapi.testclient import TestClient

client = TestClient(main.app)

def test_upload_audio_success(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'UPLOAD_DIR', tmp_path)
    file_path = tmp_path / 'test.wav'
    file_path.write_bytes(b'RIFF\x00\x00\x00\x00WAVEfmt ')

    with file_path.open('rb') as file:
        response = client.post('/api/upload', files={'file': ('test.wav', file, 'audio/wav')})

    assert response.status_code == 200
    data = response.json()
    assert data['file_id']
    assert data['filename'].endswith('test.wav')
    assert data['content_type'] == 'audio/wav'
    assert data['size'] == len(b'RIFF\x00\x00\x00\x00WAVEfmt ')
    assert data['artifact_url'].startswith('/uploads/')
    assert (tmp_path / data['filename']).exists()


def test_upload_audio_unsupported_type():
    response = client.post('/api/upload', files={'file': ('test.txt', io.BytesIO(b'hello'), 'text/plain')})
    assert response.status_code == 400
    data = response.json()
    assert data['error_code'] == 'unsupported_audio_format'
    assert 'Unsupported file type' in data['message']


def test_upload_audio_mimetype_extension_mismatch():
    response = client.post(
        '/api/upload',
        files={'file': ('test.wav', io.BytesIO(b'RIFF\x00\x00\x00\x00WAVEfmt '), 'audio/mpeg')},
    )

    assert response.status_code == 400
    data = response.json()
    assert data['error_code'] == 'mimetype_extension_mismatch'
    assert 'Expected file extension' in data['detail']


def test_upload_audio_corrupt_wav(tmp_path):
    file_path = tmp_path / 'bad.wav'
    file_path.write_bytes(b'RIFF....NOTWAVE')

    with file_path.open('rb') as file:
        response = client.post('/api/upload', files={'file': ('bad.wav', file, 'audio/wav')})

    assert response.status_code == 400
    data = response.json()
    assert data['error_code'] == 'corrupt_audio'
    assert 'corrupt' in data['message'].lower()


def test_upload_audio_corrupt_mp3():
    response = client.post(
        '/api/upload',
        files={'file': ('test.mp3', io.BytesIO(b'NOTMP3DATA'), 'audio/mpeg')},
    )

    assert response.status_code == 400
    data = response.json()
    assert data['error_code'] == 'corrupt_audio'
    assert 'corrupt' in data['message'].lower()


def test_analyze_audio_success(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'UPLOAD_DIR', tmp_path)
    file_path = tmp_path / 'analysis.wav'
    file_path.write_bytes(b'RIFF\x00\x00\x00\x00WAVEfmt ')

    with file_path.open('rb') as file:
        upload_response = client.post('/api/upload', files={'file': ('analysis.wav', file, 'audio/wav')})

    assert upload_response.status_code == 200
    uploaded = upload_response.json()

    analysis_response = client.post(
        '/api/analyze',
        json={
            'file_id': uploaded['file_id'],
            'filename': uploaded['filename'],
            'artifact_url': uploaded['artifact_url'],
        },
    )

    assert analysis_response.status_code == 200
    data = analysis_response.json()
    assert data['analysis']['status'] == 'completed'
    assert data['analysis']['bpm'] > 0
    assert data['analysis']['key']
    assert data['analysis']['structure']
    assert data['analysis']['task_id']
    assert data['analysis']['analyzed_at']
    assert data['workflow_stages'][1]['stage'] == 'analysis'
    assert data['workflow_stages'][1]['status'] == 'completed'

    session = main.SESSIONS[uploaded['file_id']]
    assert session['analysis']['status'] == 'completed'
    assert session['analysis']['bpm'] == data['analysis']['bpm']
    assert session['workflow_stages'][1]['status'] == 'completed'


def test_analyze_audio_missing_file_id():
    response = client.post('/api/analyze', json={'file_id': 'missing'})

    assert response.status_code == 404
    data = response.json()
    assert data['error_code'] == 'analysis_session_not_found'
    assert 'not found' in data['message'].lower()


def test_analyze_audio_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'UPLOAD_DIR', tmp_path)
    file_path = tmp_path / 'analysis.wav'
    file_path.write_bytes(b'RIFF\x00\x00\x00\x00WAVEfmt ')

    with file_path.open('rb') as file:
        upload_response = client.post('/api/upload', files={'file': ('analysis.wav', file, 'audio/wav')})

    uploaded = upload_response.json()
    payload = {
        'file_id': uploaded['file_id'],
        'filename': uploaded['filename'],
        'artifact_url': uploaded['artifact_url'],
    }

    first = client.post('/api/analyze', json=payload)
    second = client.post('/api/analyze', json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()['analysis'] == second.json()['analysis']


def test_analyze_audio_missing_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'UPLOAD_DIR', tmp_path)
    file_id = 'missing-artifact-session'
    main.SESSIONS[file_id] = {
        'file_id': file_id,
        'filename': 'missing.wav',
        'artifact_url': '/uploads/missing.wav',
        'analysis': None,
        'workflow_stages': [],
    }

    response = client.post('/api/analyze', json={'file_id': file_id})

    assert response.status_code == 422
    data = response.json()
    assert data['error_code'] == 'analysis_artifact_missing'
    assert main.SESSIONS[file_id]['analysis']['status'] == 'failed'
