from datetime import datetime, timezone
from pathlib import Path
import shutil
import socket
from urllib.parse import urlparse

try:
    from celery import Celery

    app = Celery('workers', broker='redis://localhost:6379/0', backend='redis://localhost:6379/0')
    # Fail fast when the Redis broker is unreachable instead of blocking in
    # kombu's connection-retry loop (default max_retries=100 with backoff can
    # hang for minutes). This lets the app's in-process fallback
    # (run_analysis_task / run_separation_task) take over immediately when a
    # broker/worker is not running, while preserving normal async dispatch
    # whenever Redis + the worker ARE running.
    app.conf.broker_connection_retry_on_startup = False
    app.conf.broker_connection_max_retries = 0
    CELERY_AVAILABLE = True
except ImportError:
    app = None
    CELERY_AVAILABLE = False


def broker_reachable(timeout: float = 1.0) -> bool:
    """Return True quickly if the Redis broker accepts TCP connections.

    Used to gate Celery dispatch so the app falls back to in-process execution
    fast (instead of blocking in kombu's result-backend reconnect loop) when no
    broker is running. When Celery is absent, there is nothing to reach.
    """
    if app is None:
        return False
    url = app.conf.broker_url
    if url is None:
        return False
    parsed = urlparse(url)
    host = parsed.hostname or '127.0.0.1'
    port = parsed.port or 6379
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False

STEM_NAMES = ['drums', 'bass', 'other', 'vocals']


def build_analysis_result(file_id: str, file_path: str) -> dict:
    """Deterministic placeholder analysis for MVP contract validation."""
    return {
        'file_id': file_id,
        'status': 'completed',
        'file_path': file_path,
        'bpm': 118.0,
        'key': 'D minor',
        'structure': ['intro', 'verse', 'chorus', 'outro'],
        'analyzed_at': datetime.now(timezone.utc).isoformat(),
    }


def analyze_audio(file_id: str, file_path: str) -> dict:
    return build_analysis_result(file_id, file_path)


def _available_demucs_model():
    """Return the Demucs model when installed, else None (optional dependency)."""
    try:
        from demucs.pretrained import get_model

        return get_model('htdemucs')
    except Exception:
        return None


def _separate_with_demucs(file_id: str, file_path: str, stems_dir: Path) -> dict | None:
    """Attempt real HTDemucs v4 separation. Returns a result dict or None on any failure."""
    model = _available_demucs_model()
    if model is None:
        return None
    try:
        import torch
        from demucs.apply import apply_model
        from demucs.audio import AudioFile, save_audio

        model.eval()
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        model = model.to(device)

        wav = AudioFile(file_path).read(
            streams=0,
            samplerate=model.samplerate,
            channels=model.audio_channels,
        )
        ref = wav.mean(0)
        wav = (wav - ref.mean()) / ref.std()

        sources_wav = apply_model(
            model,
            wav[None],
            device=device,
            shifts=0,
            split=True,
            progress=False,
        )[0]
        sources_wav = sources_wav * ref.std() + ref.mean()

        stems_dir = Path(stems_dir)
        stems_dir.mkdir(parents=True, exist_ok=True)
        out = []
        for source, source_wav in zip(model.sources, sources_wav):
            stem_path = stems_dir / f'{source}.wav'
            save_audio(source_wav.cpu(), str(stem_path), samplerate=model.samplerate)
            out.append({
                'name': source,
                'filename': stem_path.name,
                'size': stem_path.stat().st_size,
                'format': 'wav',
            })
        return {
            'file_id': file_id,
            'status': 'completed',
            'stems': out,
            'separated_at': datetime.now(timezone.utc).isoformat(),
        }
    except Exception:
        return None


def build_separation_result(file_id: str, file_path: str, stems_dir: Path) -> dict:
    """Deterministic placeholder separation that preserves the API/persistence contract.

    Writes one real, serviceable stem file per name (a copy of the source audio) so the
    artifact URLs resolve for later review/export. Mirrors the analysis placeholder
    technique used in Story 2.1.
    """
    stems_dir = Path(stems_dir)
    stems_dir.mkdir(parents=True, exist_ok=True)
    src = Path(file_path)
    ext = src.suffix.lower() or '.wav'
    out = []
    if src.exists():
        for name in STEM_NAMES:
            target = stems_dir / f'{name}{ext}'
            if not target.exists() or target.stat().st_size != src.stat().st_size:
                shutil.copyfile(src, target)
            out.append({
                'name': name,
                'filename': target.name,
                'size': target.stat().st_size,
                'format': ext.lstrip('.'),
            })
    else:
        for name in STEM_NAMES:
            out.append({
                'name': name,
                'filename': f'{name}{ext}',
                'size': None,
                'format': ext.lstrip('.'),
            })
    return {
        'file_id': file_id,
        'status': 'completed',
        'stems': out,
        'separated_at': datetime.now(timezone.utc).isoformat(),
    }


def separate_stems(file_id: str, file_path: str, stems_dir: Path) -> dict:
    """Separate audio into discrete stems. Tries Demucs (optional) then falls back to placeholder."""
    result = _separate_with_demucs(file_id, file_path, Path(stems_dir))
    if result is not None:
        result['method'] = 'demucs'
        return result
    result = build_separation_result(file_id, file_path, Path(stems_dir))
    result['method'] = 'placeholder'
    return result


if CELERY_AVAILABLE and app is not None:
    analyze_audio_task = app.task(name='analyze_audio')(analyze_audio)
    separate_stems_task = app.task(name='separate_stems')(separate_stems)
else:
    analyze_audio_task = None
    separate_stems_task = None
