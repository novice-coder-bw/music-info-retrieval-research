from datetime import datetime, timezone

try:
    from celery import Celery

    app = Celery('workers', broker='redis://localhost:6379/0', backend='redis://localhost:6379/0')
    CELERY_AVAILABLE = True
except ImportError:
    app = None
    CELERY_AVAILABLE = False


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


if CELERY_AVAILABLE and app is not None:
    analyze_audio_task = app.task(name='analyze_audio')(analyze_audio)
else:
    analyze_audio_task = None
