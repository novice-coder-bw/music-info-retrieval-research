import hashlib
import io
from datetime import datetime, timezone
from pathlib import Path
import main
from fastapi.testclient import TestClient
import pytest
from workers import tasks as tasks_module

# Retain the real Demucs separation backend. The hermetic flow tests patch
# tasks_module._separate_with_demucs to a fast test double so they don't run the
# full HTDemucs model on CPU; this retained reference is used by the one dedicated
# real-separation test and the real-path honest-failure unit test.
_REAL_SEPARATE_WITH_DEMUCS = tasks_module._separate_with_demucs

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def _hermetic_backend_env(monkeypatch):
    """Force local/degraded backends for every test so the suite never depends on
    (or writes to) real R2/Neon regardless of the ambient environment, and the
    pre-existing Story 1.1-2.2 expectations (e.g. /uploads/ artifact URLs) hold."""
    for key in (
        'DATABASE_URL',
        'R2_ACCOUNT_ID',
        'R2_ENDPOINT',
        'R2_BUCKET',
        'R2_ACCESS_KEY_ID',
        'R2_SECRET_ACCESS_KEY',
        'R2_PUBLIC_BASE_URL',
    ):
        monkeypatch.delenv(key, raising=False)
    # Never dispatch to a real Celery worker during tests: force the app's
    # in-process fallback regardless of whether a Redis broker happens to be
    # running (a broker without a worker would make analyze/separate block on
    # their 30s result timeout).
    monkeypatch.setattr(main, 'broker_reachable', lambda timeout=1.0: False)
    import db.engine as db_engine_module

    db_engine_module.reset_engine()


def _make_wav(path, bpm=120.0, sr=44100, dur=4.0) -> None:
    """Write a valid mono WAV (tonal bed + a percussive click at ``bpm``).

    Starter 2.4 uses this real audio for analysis/separation so the results are
    computed from actual audio instead of a dummy 12-byte header.
    """
    import numpy as np
    import wave

    n = int(sr * dur)
    t = np.arange(n) / sr
    x = 0.35 * np.sin(2 * np.pi * 220.0 * t) + 0.18 * np.sin(2 * np.pi * 330.0 * t)
    beat = int(60.0 / bpm * sr)
    clicks = np.zeros(n)
    for start in range(0, n, beat):
        clicks[start : start + int(0.01 * sr)] = 0.9
    x = np.clip(x + clicks, -1.0, 1.0).astype('float32')
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((x * 32767).astype('int16').tobytes())


def _fake_real_stems(file_id, file_path, stems_dir):
    """Fast, hermetic test double for the real Demucs separation backend.

    Writes four byte-distinct 32-bit float WAV stems (drums, bass, other,
    vocals) so the route/persistence flow tests stay fast without running
    HTDemucs on CPU, and proves the stems are never byte-identical copies of the
    mix (real distinctness of the actual model is covered by the dedicated
    ``test_separate_writes_four_distinct_real_stems`` test).
    """
    import struct

    source_bytes = Path(file_path).read_bytes() if Path(file_path).exists() else b'RIFF....WAVE'
    stems_dir = Path(stems_dir)
    stems_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for i, name in enumerate(['drums', 'bass', 'other', 'vocals']):
        payload = b'RIFF\x00\x00\x00\x00WAVE' + b'fmt ' + struct.pack('<I', 16) + struct.pack(
            '<HHIIHH', 3, 1, 8000, 8000 * 4, 4, 32
        ) + b'data' + struct.pack('<I', 4) + bytes([(len(source_bytes) + i) % 251] * 18)
        stem_path = stems_dir / f'{name}.wav'
        stem_path.write_bytes(payload)
        out.append({'name': name, 'filename': stem_path.name, 'size': stem_path.stat().st_size, 'format': 'wav'})
    return {
        'file_id': file_id,
        'status': 'completed',
        'stems': out,
        'separated_at': datetime.now(timezone.utc).isoformat(),
    }


@pytest.fixture(autouse=True)
def _fake_separation_backend(monkeypatch):
    """Use the fast, hermetic separation double for every flow/persistence test."""
    monkeypatch.setattr(tasks_module, '_separate_with_demucs', _fake_real_stems)

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
    _make_wav(file_path)

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
    # Real (non-hardcoded) BPM: an ~120 BPM fixture yields 90-150 BPM, not the
    # old placeholder 118.0 hardcode.
    assert 90 <= data['analysis']['bpm'] <= 150
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
    _make_wav(file_path)

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
    file_id = 'analysis-missing-artifact-session'
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
def _seed_analyzed_session(tmp_path, monkeypatch, filename='analysis.wav'):
    monkeypatch.setattr(main, 'UPLOAD_DIR', tmp_path)
    monkeypatch.setattr(main, 'STEM_DIR', tmp_path / 'stems')
    main.STEM_DIR.mkdir(parents=True, exist_ok=True)
    file_path = tmp_path / filename
    _make_wav(file_path)
    with file_path.open('rb') as file:
        upload_response = client.post('/api/upload', files={'file': (filename, file, 'audio/wav')})
    file_id = upload_response.json()['file_id']
    client.post(
        '/api/analyze',
        json={
            'file_id': file_id,
            'filename': upload_response.json()['filename'],
            'artifact_url': upload_response.json()['artifact_url'],
        },
    )
    return file_id


def test_separate_audio_success(tmp_path, monkeypatch):
    file_id = _seed_analyzed_session(tmp_path, monkeypatch)

    response = client.post('/api/separate', json={'file_id': file_id})

    assert response.status_code == 200
    data = response.json()
    assert data['stems']['status'] == 'completed'
    assert data['stems']['method'] == 'demucs'
    stem_names = [stem['name'] for stem in data['stems']['stems']]
    assert stem_names == ['drums', 'bass', 'other', 'vocals']
    for stem in data['stems']['stems']:
        assert stem['url'].startswith('/uploads/stems/')

    stages = data['workflow_stages']
    assert stages[0]['stage'] == 'upload'
    assert stages[0]['status'] == 'completed'
    assert stages[1]['stage'] == 'analysis'
    assert stages[2]['stage'] == 'stem_separation'
    assert stages[2]['status'] == 'completed'

    session = main.SESSIONS[file_id]
    assert session['stems']['status'] == 'completed'
    assert len(session['stems']['stems']) == 4
    stem_dir = main.STEM_DIR / file_id
    assert (stem_dir / 'drums.wav').exists()
    assert (stem_dir / 'vocals.wav').exists()


def test_separate_audio_missing_file_id():
    response = client.post('/api/separate', json={'file_id': 'missing'})

    assert response.status_code == 404
    data = response.json()
    assert data['error_code'] == 'separation_session_not_found'
    assert data['stage'] == 'stem_separation'
    assert data['next_action']


def test_separate_audio_analysis_not_complete(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'UPLOAD_DIR', tmp_path)
    file_path = tmp_path / 'raw.wav'
    file_path.write_bytes(b'RIFF\x00\x00\x00\x00WAVEfmt ')
    with file_path.open('rb') as file:
        upload_response = client.post('/api/upload', files={'file': ('raw.wav', file, 'audio/wav')})
    file_id = upload_response.json()['file_id']

    response = client.post('/api/separate', json={'file_id': file_id})

    assert response.status_code == 422
    data = response.json()
    assert data['error_code'] == 'separation_analysis_not_complete'
    assert main.SESSIONS[file_id].get('stems') is None


def test_separate_audio_idempotent(tmp_path, monkeypatch):
    file_id = _seed_analyzed_session(tmp_path, monkeypatch)

    first = client.post('/api/separate', json={'file_id': file_id})
    second = client.post('/api/separate', json={'file_id': file_id})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()['stems'] == second.json()['stems']


def test_separate_audio_missing_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'UPLOAD_DIR', tmp_path)
    file_id = 'separation-missing-artifact-session'
    main.SESSIONS[file_id] = {
        'file_id': file_id,
        'filename': 'missing.wav',
        'artifact_url': '/uploads/missing.wav',
        'analysis': {
            'status': 'completed',
            'bpm': 118.0,
            'key': 'D minor',
            'structure': ['intro', 'verse', 'chorus', 'outro'],
        },
        'workflow_stages': [],
    }

    response = client.post('/api/separate', json={'file_id': file_id})

    assert response.status_code == 422
    data = response.json()
    assert data['error_code'] == 'separation_artifact_missing'
    assert main.SESSIONS[file_id]['stems']['status'] == 'failed'
# --- Story 2.3: persistence & object-storage test coverage -----------------
# The durable store is exercised through the store adapter (not the in-memory
# SESSIONS dict) so these tests prove the process-restart-survival contract.


def _configure_persistent_store(tmp_path) -> str:
    """Point the app store at a temp-file SQLite backend; return its URL."""
    import db.engine as db_engine_module

    db_url = f"sqlite:///{(tmp_path / 'persistence.db').as_posix()}"
    db_engine_module.configure_engine(db_url)
    return db_url


def _restore_default_store() -> None:
    import db.engine as db_engine_module

    db_engine_module.reset_engine()


def test_upload_persists_session_and_raw_audio_artifact(tmp_path, monkeypatch):
    """Upload writes a session row + one raw_audio artifact to the store."""
    from db import store as db_store

    monkeypatch.setattr(main, 'UPLOAD_DIR', tmp_path)
    file_path = tmp_path / 'persist.wav'
    file_path.write_bytes(b'RIFF\x00\x00\x00\x00WAVEfmt ')

    with file_path.open('rb') as file:
        response = client.post('/api/upload', files={'file': ('persist.wav', file, 'audio/wav')})

    assert response.status_code == 200
    file_id = response.json()['file_id']

    stored = db_store.get_session(file_id)
    assert stored is not None
    assert stored['file_id'] == file_id
    assert stored['analysis'] is None
    assert stored['workflow_stages'][0]['status'] == 'completed'

    artifacts = db_store.list_artifacts(file_id)
    assert len(artifacts) == 1
    assert artifacts[0]['kind'] == 'raw_audio'
    assert artifacts[0]['storage_backend'] == 'local'
    assert artifacts[0]['url'].startswith('/uploads/')


def test_persistence_round_trip_survives_restart(tmp_path, monkeypatch):
    """Full flow persists; a fresh engine on the same DB file restores it."""
    from sqlalchemy.orm import sessionmaker

    import db.engine as db_engine_module
    from db import store as db_store
    from db.models import Base

    db_url = _configure_persistent_store(tmp_path)
    try:
        file_id = _seed_analyzed_session(tmp_path, monkeypatch)

        separate_response = client.post('/api/separate', json={'file_id': file_id})
        assert separate_response.status_code == 200

        # Simulate a process restart: a brand-new engine bound to the same file,
        # read through the store adapter (NOT the in-memory SESSIONS dict).
        fresh_engine = db_engine_module.create_engine_for_url(db_url)
        Base.metadata.create_all(fresh_engine)
        fresh_factory = sessionmaker(bind=fresh_engine, autoflush=False, autocommit=False, expire_on_commit=False)

        stored = db_store.get_session(file_id, fresh_factory)
        assert stored is not None
        assert stored['analysis']['status'] == 'completed'
        assert stored['analysis']['bpm'] > 0
        assert stored['stems']['status'] == 'completed'
        stem_names = [stem['name'] for stem in stored['stems']['stems']]
        assert stem_names == ['drums', 'bass', 'other', 'vocals']
        stage_status = {stage['stage']: stage['status'] for stage in stored['workflow_stages']}
        assert stage_status['upload'] == 'completed'
        assert stage_status['analysis'] == 'completed'
        assert stage_status['stem_separation'] == 'completed'

        # Raw audio + 4 stems = 5 stable, normalized artifact rows.
        artifacts = db_store.list_artifacts(file_id, fresh_factory)
        assert len(artifacts) == 5
        assert {artifact['kind'] for artifact in artifacts} == {'raw_audio', 'stem'}
        assert all(artifact['url'].startswith('/uploads/') for artifact in artifacts)
    finally:
        _restore_default_store()


def test_session_restores_after_process_restart(tmp_path, monkeypatch):
    """After a restart (fresh engine, no in-memory cache) the session resolves."""
    _configure_persistent_store(tmp_path)
    file_id = None
    try:
        file_id = _seed_analyzed_session(tmp_path, monkeypatch)
        assert client.post('/api/separate', json={'file_id': file_id}).status_code == 200

        # Simulate restart: drop the cached engine and the in-memory session.
        main.SESSIONS.pop(file_id, None)
        _restore_default_store()
        _configure_persistent_store(tmp_path)  # re-open the same DB file

        response = client.get(f'/api/session/{file_id}')
        assert response.status_code == 200
        body = response.json()
        assert body['analysis']['status'] == 'completed'
        assert body['stems']['status'] == 'completed'
        assert body['artifact_url'].startswith('/uploads/')
    finally:
        if file_id:
            main.SESSIONS.pop(file_id, None)
        _restore_default_store()
def test_persisted_state_is_idempotent_across_calls(tmp_path, monkeypatch):
    """Repeated analyze/separate calls never duplicate or corrupt persisted state."""
    from db import store as db_store

    _configure_persistent_store(tmp_path)
    try:
        file_id = _seed_analyzed_session(tmp_path, monkeypatch)

        second = client.post(
            '/api/analyze',
            json={'file_id': file_id, 'filename': 'analysis.wav', 'artifact_url': '/uploads/analysis.wav'},
        )
        assert second.status_code == 200

        first_sep = client.post('/api/separate', json={'file_id': file_id})
        second_sep = client.post('/api/separate', json={'file_id': file_id})
        assert first_sep.status_code == 200
        assert second_sep.status_code == 200

        stored = db_store.get_session(file_id)
        assert stored['analysis']['status'] == 'completed'
        assert stored['stems']['status'] == 'completed'

        artifacts = db_store.list_artifacts(file_id)
        assert len(artifacts) == 5  # 1 raw + 4 stems, no duplicates
        assert len([a for a in artifacts if a['kind'] == 'raw_audio']) == 1
        assert len([a for a in artifacts if a['kind'] == 'stem']) == 4
    finally:
        _restore_default_store()


def test_backend_is_local_and_flow_works_without_env(monkeypatch, tmp_path):
    """With no R2/DB env, the app uses the local backend and the flow works."""
    from services import storage as storage_module

    for key in (
        'DATABASE_URL',
        'R2_ACCOUNT_ID',
        'R2_ENDPOINT',
        'R2_BUCKET',
        'R2_ACCESS_KEY_ID',
        'R2_SECRET_ACCESS_KEY',
        'R2_PUBLIC_BASE_URL',
    ):
        monkeypatch.delenv(key, raising=False)

    assert storage_module.active_backend() == 'local'
    import db.engine as db_engine_module

    assert db_engine_module.get_database_url() == 'sqlite:///:memory:'

    file_id = _seed_analyzed_session(tmp_path, monkeypatch)
    response = client.post('/api/separate', json={'file_id': file_id})
    assert response.status_code == 200
    assert response.json()['stems']['status'] == 'completed'
    artifact_urls = [stem['url'] for stem in response.json()['stems']['stems']]
    assert all(url.startswith('/uploads/stems/') for url in artifact_urls)


def test_r2_mirror_returns_stable_url_when_configured(monkeypatch, tmp_path):
    """When R2 is active, mirror_file returns a stable URL and marks the backend."""
    from services import storage as storage_module

    source = tmp_path / 'clip.wav'
    source.write_bytes(b'RIFF\x00\x00\x00\x00WAVEfmt ')

    monkeypatch.setattr(storage_module, 'active_backend', lambda: 'r2')
    monkeypatch.setattr(
        storage_module,
        '_upload_to_r2',
        lambda settings, path, key, content_type: f'https://pub.example.com/{key}',
    )

    result = storage_module.mirror_file(
        local_path=source,
        object_key='stems/abc/vocals.wav',
        content_type='audio/wav',
        local_url='/uploads/stems/abc/vocals.wav',
    )
    assert result['storage_backend'] == 'r2'
    assert result['url'] == 'https://pub.example.com/stems/abc/vocals.wav'
    assert result['key'] == 'stems/abc/vocals.wav'


def test_r2_mirror_degrades_to_local_on_failure(monkeypatch, tmp_path):
    """An R2 upload failure falls back to local and is marked honestly."""
    from services import storage as storage_module

    source = tmp_path / 'clip.wav'
    source.write_bytes(b'RIFF\x00\x00\x00\x00WAVEfmt ')

    monkeypatch.setattr(storage_module, 'active_backend', lambda: 'r2')
    monkeypatch.setattr(
        storage_module,
        '_upload_to_r2',
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('r2 down')),
    )

    result = storage_module.mirror_file(
        local_path=source,
        object_key='raw/abc/clip.wav',
        content_type='audio/wav',
        local_url='/uploads/clip-abc.wav',
    )
    assert result['storage_backend'] == 'local'
    assert result['url'] == '/uploads/clip-abc.wav'
    assert result['key'] is None


def test_persistence_failure_degrades_gracefully(tmp_path, monkeypatch):
    """A failing store never breaks the upload/analyze flow (local fallback)."""
    import db.store as db_store_module

    def _boom(*args, **kwargs):
        raise RuntimeError('database unavailable')

    monkeypatch.setattr(db_store_module, 'save_session', _boom)
    monkeypatch.setattr(db_store_module, 'save_artifact', _boom)
    monkeypatch.setattr(db_store_module, 'get_session', _boom)

    monkeypatch.setattr(main, 'UPLOAD_DIR', tmp_path)
    file_path = tmp_path / 'degrade.wav'
    _make_wav(file_path)

    with file_path.open('rb') as file:
        upload_response = client.post('/api/upload', files={'file': ('degrade.wav', file, 'audio/wav')})
    assert upload_response.status_code == 200
    file_id = upload_response.json()['file_id']

    response = client.post(
        '/api/analyze',
        json={
            'file_id': file_id,
            'filename': upload_response.json()['filename'],
            'artifact_url': upload_response.json()['artifact_url'],
        },
    )
    assert response.status_code == 200
    assert response.json()['analysis']['status'] == 'completed'


# --- Regression tests for 2026-08-12 review fixes ---------------------------
# These lock in the patches applied in the code review that followed the
# "No module named 'psycopg2'" / "Unable to load ... audio" reports.


def test_normalize_database_url_rewrites_to_psycopg3():
    """A bare postgres URL is rewritten to the installed psycopg (v3) driver so
    neither the app engine nor the alembic migration path hits missing psycopg2."""
    from db.engine import normalize_database_url

    assert (
        normalize_database_url('postgresql://u:p@host/db?sslmode=require')
        == 'postgresql+psycopg://u:p@host/db?sslmode=require'
    )
    assert normalize_database_url('postgres://u:p@host/db') == 'postgresql+psycopg://u:p@host/db'
    # Already-on-psycopg3 URLs and sqlite are left untouched (idempotent).
    assert normalize_database_url('postgresql+psycopg://u:p@host/db') == 'postgresql+psycopg://u:p@host/db'
    assert normalize_database_url('sqlite:///x.db') == 'sqlite:///x.db'
    assert normalize_database_url('') == ''


def test_save_artifact_upsert_is_idempotent(tmp_path, monkeypatch):
    """Re-registering the same artifact (file_id, name, kind) updates rather than
    duplicates, so a retried separation never inflates the artifact count."""
    import db.engine as db_engine_module

    db_url = _configure_persistent_store(tmp_path)
    try:
        from db import store as db_store

        artifact = {
            'file_id': 'art-upsert-session',
            'name': 'vocals.wav',
            'kind': 'stem',
            'url': '/uploads/stems/art-upsert-session/vocals.wav',
            'storage_backend': 'local',
            'key': None,
            'size': 1024,
            'format': 'wav',
            'mime_type': 'audio/wav',
        }
        db_store.save_artifact(artifact)
        db_store.save_artifact({**artifact, 'size': 2048, 'url': '/uploads/stems/art-upsert-session/vocals-2.wav'})

        rows = db_store.list_artifacts('art-upsert-session')
        assert len(rows) == 1
        assert rows[0]['size'] == 2048
        assert rows[0]['url'].endswith('vocals-2.wav')
    finally:
        _restore_default_store()


def test_resolve_session_prefers_fresh_in_memory_over_stale_store(tmp_path, monkeypatch):
    """A session present in the in-memory SESSIONS dict (the authoritative within
    a process) wins over an older store row, so a silently-failed store write can
    never resurrect stale state on a later read."""
    import db.engine as db_engine_module

    db_url = _configure_persistent_store(tmp_path)
    file_id = 'resolve-prefers-fresh'
    try:
        from db import store as db_store

        # Store holds an OLDER/empty row (as if a write landed before analysis).
        db_store.save_session({'file_id': file_id, 'analysis': None, 'workflow_stages': []})

        # In-memory holds the NEWER state.
        main.SESSIONS[file_id] = {
            'file_id': file_id,
            'analysis': {'status': 'completed', 'bpm': 120.0, 'key': 'A minor'},
            'workflow_stages': [{'stage': 'analysis', 'status': 'completed', 'message': 'done'}],
        }

        resolved = main._resolve_session(file_id)
        assert resolved['analysis']['status'] == 'completed'
        assert resolved['analysis']['bpm'] == 120.0
    finally:
        main.SESSIONS.pop(file_id, None)
        _restore_default_store()


def test_engine_degrades_to_sqlite_when_postgres_schema_missing(monkeypatch):
    """A reachable-but-unmigrated Postgres (missing sessions/artifacts tables) is
    detected at engine build and degrades to the local SQLite fallback with an
    actionable warning, instead of silently running a non-durable store and
    spamming per-request UndefinedTable errors."""
    import db.engine as db_engine_module

    class _FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class _FakeInspector:
        def has_table(self, name):  # noqa: ARG002 - schema intentionally missing
            return False

    class _FakeEngine:
        def connect(self):
            return _FakeConn()

        def dispose(self):
            pass

    monkeypatch.setenv('DATABASE_URL', 'postgresql://u:p@host/db')
    calls: list[str] = []

    def fake_create_engine(url, *args, **kwargs):
        calls.append(url)
        return _FakeEngine()

    monkeypatch.setattr(db_engine_module, 'create_engine_for_url', fake_create_engine)
    monkeypatch.setattr(db_engine_module, 'inspect', lambda engine: _FakeInspector())
    monkeypatch.setattr(db_engine_module.Base.metadata, 'create_all', lambda engine: None)
    db_engine_module.reset_engine()
    try:
        db_engine_module.get_engine()
        assert calls == [
            'postgresql+psycopg://u:p@host/db',  # candidate engine
            'sqlite:///:memory:',  # honest degraded fallback
        ]
    finally:
        db_engine_module.reset_engine()


# --- Story 2.4: real essentia analysis + real Demucs stems -------------------


def test_analysis_is_data_driven_not_hardcoded(tmp_path):
    """Two fixtures at different tempos yield different real BPM/metadata."""

    slow = tmp_path / 'slow.wav'
    fast = tmp_path / 'fast.wav'
    _make_wav(slow, bpm=120)
    _make_wav(fast, bpm=172)

    slow_result = tasks_module.build_analysis_result('slow-id', str(slow))
    fast_result = tasks_module.build_analysis_result('fast-id', str(fast))

    assert slow_result['status'] == 'completed'
    assert fast_result['status'] == 'completed'
    assert slow_result['bpm'] not in (None, 118.0)  # not the old hardcode
    assert slow_result['key']
    assert slow_result['structure']
    # Data-driven, not hardcoded: different tempos produce different BPM.
    assert slow_result['bpm'] != fast_result['bpm']
    assert fast_result['bpm'] > slow_result['bpm']


def test_separate_writes_four_distinct_real_stems(tmp_path):
    """The REAL HTDemucs path writes four byte-distinct stems, distinct from source."""
    src = tmp_path / 'real.wav'
    _make_wav(src, bpm=120, dur=1.5)  # short clip to keep CPU time bounded
    stems_dir = tmp_path / 'stems'

    result = _REAL_SEPARATE_WITH_DEMUCS('real-id', str(src), stems_dir)

    assert result['status'] == 'completed'
    names = [stem['name'] for stem in result['stems']]
    assert names == ['drums', 'bass', 'other', 'vocals']
    hashes = {}
    for stem in result['stems']:
        p = stems_dir / stem['filename']
        assert p.exists() and p.stat().st_size > 0
        hashes[stem['name']] = hashlib.md5(p.read_bytes()).hexdigest()
    # Four distinct stems: byte-different from each other...
    assert len(set(hashes.values())) == 4
    # ...and byte-different from the source mix (never shutil.copyfile copies).
    src_hash = hashlib.md5(src.read_bytes()).hexdigest()
    assert all(h != src_hash for h in hashes.values())


def test_separate_writes_four_distinct_real_stems_long_track(tmp_path):
    """Regression: a track LONGER than SPLIT_SEGMENT_SECONDS (which forces the
    chunked apply path) must NOT raise the old
    "shape '[1, 4, -1, N]' is invalid for input of size M" /
    "'>' not supported between instances of 'tuple' and 'float'" errors.
    It must produce four byte-distinct stems."""
        # 25s of audio, just above the 20s chunking threshold, to force the
    # chunked apply path without making the test prohibitively slow on CPU.
    src = tmp_path / 'long.wav'
    _make_wav(src, bpm=120, dur=25.0)
    stems_dir = tmp_path / 'stems'

    result = _REAL_SEPARATE_WITH_DEMUCS('long-id', str(src), stems_dir)

    assert result['status'] == 'completed'
    names = [stem['name'] for stem in result['stems']]
    assert names == ['drums', 'bass', 'other', 'vocals']
    hashes = {}
    for stem in result['stems']:
        p = stems_dir / stem['filename']
        assert p.exists() and p.stat().st_size > 0
        hashes[stem['name']] = hashlib.md5(p.read_bytes()).hexdigest()
    # Four distinct stems, and all distinct from the source mix.
    assert len(set(hashes.values())) == 4
    src_hash = hashlib.md5(src.read_bytes()).hexdigest()
    assert all(h != src_hash for h in hashes.values())


def test_real_separation_returns_honest_failure_when_model_unavailable(tmp_path, monkeypatch):
    """With no model, the real separation path reports an honest failed status."""
    monkeypatch.setattr(tasks_module, '_available_demucs_model', lambda: None)
    src = tmp_path / 'm.wav'
    _make_wav(src)
    result = _REAL_SEPARATE_WITH_DEMUCS('id', str(src), tmp_path / 'stems')
    assert result['status'] == 'failed'
    assert result['stems'] == []
    assert result['message']
    assert result['next_action']
    assert 'completed' != result['status']


def test_separate_reports_honest_failure_via_api(tmp_path, monkeypatch):
    """The API surfaces an honest separation failure instead of fake completed stems."""
    file_id = _seed_analyzed_session(tmp_path, monkeypatch)

    def _unavailable(file_id, file_path, stems_dir):
        return {
            'file_id': file_id,
            'status': 'failed',
            'stems': [],
            'message': 'Real stem separation is unavailable because the Demucs model could not be loaded.',
            'next_action': 'Install demucs>=4.0.0 and torch>=2.0.0 in the runtime and retry stem separation.',
            'separated_at': datetime.now(timezone.utc).isoformat(),
        }

    monkeypatch.setattr(tasks_module, '_separate_with_demucs', _unavailable)

    response = client.post('/api/separate', json={'file_id': file_id})

    assert response.status_code == 422
    data = response.json()
    assert data['error_code'] == 'separation_processing_failed'
    assert data['stage'] == 'stem_separation'
    assert 'Demucs model could not be loaded' in data['message']
    assert main.SESSIONS[file_id]['stems']['status'] == 'failed'
