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
