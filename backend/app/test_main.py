import io
from pathlib import Path
import main
from fastapi.testclient import TestClient

client = TestClient(main.app)

def test_upload_audio_success(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'UPLOAD_DIR', tmp_path)
    file_path = tmp_path / 'test.mp3'
    file_path.write_bytes(b'RIFF....')

    with file_path.open('rb') as file:
        response = client.post('/api/upload', files={'file': ('test.mp3', file, 'audio/mpeg')})

    assert response.status_code == 200
    data = response.json()
    assert data['file_id']
    assert data['filename'].endswith('test.mp3')
    assert data['content_type'] == 'audio/mpeg'
    assert data['size'] == len(b'RIFF....')
    assert data['artifact_url'].startswith('/uploads/')
    assert (tmp_path / data['filename']).exists()


def test_upload_audio_unsupported_type():
    response = client.post('/api/upload', files={'file': ('test.txt', io.BytesIO(b'hello'), 'text/plain')})
    assert response.status_code == 400
    assert 'Unsupported file type' in response.json()['detail']
