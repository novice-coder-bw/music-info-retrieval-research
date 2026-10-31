from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import shutil
import tempfile
from urllib.parse import urlparse

from celery import Celery
from celery.signals import worker_process_init

from db.engine import get_engine
from db import store as db_store
from services import storage

logger = logging.getLogger('workers.tasks')

broker_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
app = Celery('workers', broker=broker_url, backend=broker_url)

if os.environ.get('CELERY_EAGER', '').lower() in ('1', 'true', 'yes'):
    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = True

# Worker concurrency rule: 1 worker process
app.conf.worker_concurrency = 1


@worker_process_init.connect
def on_worker_init(**kwargs):
    """Dispose inherited SQLAlchemy pool after Celery forks."""
    try:
        engine = get_engine()
        engine.dispose(close=False)
        logger.info('Disposed database engine after worker fork')
    except Exception as exc:
        logger.warning('Failed to dispose database engine in worker: %s', exc)


DEMUCS_AVAILABLE = False
try:
    import torch  # noqa: F401
    from demucs.apply import apply_model
    from demucs.pretrained import get_model
    DEMUCS_AVAILABLE = True
except ImportError:
    pass

ESSENTIA_AVAILABLE = False
try:
    import essentia.standard as es
    ESSENTIA_AVAILABLE = True
except ImportError:
    pass


def update_session_stage(file_id: str, stage_name: str, status: str, message: str) -> None:
    """Update workflow stage in database so Supabase Realtime notifies frontend."""
    try:
        session = db_store.get_session(file_id)
        if not session:
            return
        stages = list(session.get('workflow_stages') or [])
        found = False
        for s in stages:
            if s.get('stage') == stage_name:
                s['status'] = status
                s['message'] = message
                found = True
                break
        if not found:
            stages.append({'stage': stage_name, 'status': status, 'message': message})
        session['workflow_stages'] = stages
        db_store.save_session(session)
    except Exception as exc:
        logger.warning('Failed to update stage in database for session %s: %s', file_id, exc)


def build_analysis_result(file_id: str, file_path: str) -> dict:
    """Analyze audio features (BPM, key, structure) using Essentia or basic audio."""
    now_iso = datetime.now(timezone.utc).isoformat()
    if not ESSENTIA_AVAILABLE:
        # Check if ALLOW_PLACEHOLDER_STEMS=1 (tests / CI)
        if os.environ.get('ALLOW_PLACEHOLDER_STEMS', '0') == '1':
            return {
                'file_id': file_id,
                'status': 'completed',
                'bpm': 120.0,
                'key': 'C Major',
                'structure': [{'label': 'verse', 'start': 0.0, 'end': 10.0}],
                'analyzed_at': now_iso,
            }
        return {
            'file_id': file_id,
            'status': 'failed',
            'bpm': None,
            'key': None,
            'structure': None,
            'message': 'Essentia is not installed; real analysis unavailable.',
            'analyzed_at': now_iso,
        }

    try:
        loader = es.MonoLoader(filename=file_path)
        audio = loader()
        rhythm_extractor = es.RhythmExtractor2013(method='multifeature')
        bpm, _, _, _, _ = rhythm_extractor(audio)
        key_extractor = es.KeyExtractor()
        key, scale, _ = key_extractor(audio)
        full_key = f'{key} {scale}'
        return {
            'file_id': file_id,
            'status': 'completed',
            'bpm': round(float(bpm), 2),
            'key': full_key,
            'structure': [{'label': 'segment', 'start': 0.0, 'end': round(len(audio) / 44100.0, 2)}],
            'analyzed_at': now_iso,
        }
    except Exception as exc:
        return {
            'file_id': file_id,
            'status': 'failed',
            'bpm': None,
            'key': None,
            'structure': None,
            'message': f'Analysis failed: {exc}',
            'analyzed_at': now_iso,
        }


def separate_stems_with_demucs(file_id: str, file_path: str, temp_dir: Path) -> dict:
    """Separate audio into stems (drums, bass, other, vocals) using Demucs."""
    now_iso = datetime.now(timezone.utc).isoformat()
    stem_names = ['drums', 'bass', 'other', 'vocals']

    if not DEMUCS_AVAILABLE:
        if os.environ.get('ALLOW_PLACEHOLDER_STEMS', '0') == '1':
            # Dummy stems for CI / tests
            stems = []
            for name in stem_names:
                dummy_path = temp_dir / f'{name}.wav'
                dummy_path.write_bytes(b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00')
                uploaded = storage.upload_file(
                    local_path=dummy_path,
                    object_key=f'stems/{file_id}/{name}.wav',
                    content_type='audio/wav',
                )
                stems.append({
                    'name': name,
                    'filename': f'{name}.wav',
                    'url': uploaded['url'],
                    'storage_backend': 'r2',
                    'key': uploaded['key'],
                    'size': dummy_path.stat().st_size,
                    'format': 'wav',
                    'mime_type': 'audio/wav',
                })
            return {
                'file_id': file_id,
                'status': 'completed',
                'stems': stems,
                'separated_at': now_iso,
            }
        return {
            'file_id': file_id,
            'status': 'failed',
            'stems': [],
            'message': 'Demucs is not installed; real stem separation unavailable.',
            'separated_at': now_iso,
        }

    try:
        import torch
        import torchaudio
        wav, sr = torchaudio.load(file_path)
        model = get_model('htdemucs')
        model.eval()
        if wav.shape[0] == 1:
            wav = wav.repeat(2, 1)
        wav_np = wav.cpu().numpy()
        ref = float(wav_np.mean())
        std = float(wav_np.std())
        if std == 0.0:
            std = 1.0
        wav_norm = (wav_np - ref) / std

        # Chunked apply to prevent HTDemucs input length crashes
        max_len = 10 * int(model.samplerate)
        for inner in (model.models if hasattr(model, 'models') else [model]):
            seg = getattr(inner, 'segment', None)
            if seg is not None:
                max_len = min(max_len, int(float(seg) * float(model.samplerate)))

        total = wav_norm.shape[1]
        chunk = max(max_len, 1)

        if total <= chunk:
            with torch.no_grad():
                out = apply_model(model, torch.from_numpy(wav_norm)[None], device='cpu', split=False, progress=False)[0]
        else:
            overlap = min(chunk // 4, max_len) or 1
            step = chunk - overlap
            acc = torch.zeros(len(model.sources), wav_norm.shape[0], total, device='cpu')
            weight = torch.zeros(total, device='cpu')
            offset = 0
            while offset < total:
                end = min(offset + chunk, total)
                seg = wav_norm[:, offset:end]
                with torch.no_grad():
                    seg_out = apply_model(model, torch.from_numpy(seg)[None], device='cpu', split=False, progress=False)[0]
                acc[:, :, offset:end] += seg_out[:, :, : end - offset]
                weight[offset:end] += 1.0
                if end >= total:
                    break
                offset += step
            out = acc / weight.clamp(min=1.0)

        sources = (out.cpu().numpy() * std + ref).astype('float32')

        stems = []
        for name, src_np in zip(model.sources, sources):
            if name not in stem_names:
                continue
            stem_filename = f'{name}.wav'
            out_path = temp_dir / stem_filename
            torchaudio.save(str(out_path), torch.from_numpy(src_np), int(model.samplerate))
            uploaded = storage.upload_file(
                local_path=out_path,
                object_key=f'stems/{file_id}/{stem_filename}',
                content_type='audio/wav',
            )
            stems.append({
                'name': name,
                'filename': stem_filename,
                'url': uploaded['url'],
                'storage_backend': 'r2',
                'key': uploaded['key'],
                'size': out_path.stat().st_size,
                'format': 'wav',
                'mime_type': 'audio/wav',
            })

        return {
            'file_id': file_id,
            'status': 'completed',
            'stems': stems,
            'separated_at': now_iso,
        }
    except Exception as exc:
        return {
            'file_id': file_id,
            'status': 'failed',
            'stems': [],
            'message': f'Demucs separation failed: {exc}',
            'separated_at': now_iso,
        }


@app.task(name='workers.tasks.analyze_audio_task')
def analyze_audio_task(file_id: str, file_path_or_url: str) -> dict:
    """Celery task: analyze audio features and update Postgres."""
    update_session_stage(file_id, 'analysis', 'processing', 'Extracting audio features...')
    # If file_path_or_url is local or needs download
    local_path = file_path_or_url
    temp_download = None
    if file_path_or_url.startswith('http://') or file_path_or_url.startswith('https://'):
        parsed = urlparse(file_path_or_url)
        object_key = parsed.path.lstrip('/')
        # Download from R2 to temp file
        temp_download = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        temp_download.close()
        s3 = storage.get_s3_client()
        settings = storage.get_r2_settings()
        s3.download_file(settings['bucket'], object_key, temp_download.name)
        local_path = temp_download.name

    try:
        result = build_analysis_result(file_id, local_path)
        session = db_store.get_session(file_id)
        if session:
            session['analysis'] = result
            db_store.save_session(session)
        status = 'completed' if result.get('status') == 'completed' else 'failed'
        msg = 'Audio analysis completed' if status == 'completed' else result.get('message', 'Analysis failed')
        update_session_stage(file_id, 'analysis', status, msg)
        return result
    finally:
        if temp_download and os.path.exists(temp_download.name):
            os.remove(temp_download.name)


@app.task(name='workers.tasks.separate_stems_task')
def separate_stems_task(file_id: str, file_path_or_url: str) -> dict:
    """Celery task: run Demucs separation, upload stems to R2, clean temp scratch files."""
    update_session_stage(file_id, 'stem_separation', 'processing', 'Separating audio into stems with Demucs...')
    scratch_base = os.environ.get('SCRATCH_DIR', tempfile.gettempdir())
    work_dir = Path(tempfile.mkdtemp(prefix=f'mirr_demucs_{file_id}_', dir=scratch_base))

    local_path = file_path_or_url
    temp_download = None
    if file_path_or_url.startswith('http://') or file_path_or_url.startswith('https://'):
        parsed = urlparse(file_path_or_url)
        object_key = parsed.path.lstrip('/')
        temp_download = work_dir / 'source_audio.wav'
        s3 = storage.get_s3_client()
        settings = storage.get_r2_settings()
        s3.download_file(settings['bucket'], object_key, str(temp_download))
        local_path = str(temp_download)

    try:
        result = separate_stems_with_demucs(file_id, local_path, work_dir)
        session = db_store.get_session(file_id)
        if session:
            session['stems'] = result
            db_store.save_session(session)

        if result.get('status') == 'completed':
            for stem in result.get('stems', []):
                db_store.save_artifact({
                    'file_id': file_id,
                    'name': stem['name'],
                    'url': stem['url'],
                    'kind': 'stem',
                    'storage_backend': 'r2',
                    'key': stem['key'],
                    'size': stem.get('size'),
                    'format': stem.get('format', 'wav'),
                    'mime_type': stem.get('mime_type', 'audio/wav'),
                })
            update_session_stage(file_id, 'stem_separation', 'completed', 'Stem separation completed')
        else:
            update_session_stage(
                file_id,
                'stem_separation',
                'failed',
                result.get('message', 'Stem separation failed'),
            )
        return result
    finally:
        # Delete local temporary files after uploading stems to R2
        shutil.rmtree(work_dir, ignore_errors=True)
