from datetime import datetime, timezone
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import sys
import uuid
import logging

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

logger = logging.getLogger(__name__)

from shared.schemas import (
    AnalyzeErrorResponse,
    AnalyzeRequest,
    AnalyzeResponse,
    AnalysisMetadata,
    RegionsErrorResponse,
    RegionsRequest,
    RegionsResponse,
    RegionsMetadata,
    SeparateErrorResponse,
    SeparateRequest,
    SeparateResponse,
    StemArtifact,
    StemsMetadata,
    UploadResponse,
    UploadErrorResponse,
    WorkflowStageStatus,
)
from workers.tasks import (
    analyze_audio as run_worker_analysis,
    analyze_audio_task,
    broker_reachable,
    separate_stems as run_worker_separation,
    separate_stems_task,
)

# --- Story 2.3: durable persistence (AD-2) ----------------------------------
# Optional integration: when SQLAlchemy/boto3 (or the db/services packages)
# are not importable, the app boots and behaves exactly as before using the
# in-memory SESSIONS dict + local uploads. Mirror of the Celery/Demucs pattern.
try:
    from db.engine import get_session_factory as _db_get_session_factory
    from db import store as _db_store
    from services import storage as _storage

    STORE_AVAILABLE = True
except Exception:  # pragma: no cover - optional-dependency degraded mode
    _db_get_session_factory = None
    _db_store = None
    _storage = None
    STORE_AVAILABLE = False

app = FastAPI()
UPLOAD_DIR = Path(__file__).resolve().parent.parent / 'uploads'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
STEM_DIR = UPLOAD_DIR / 'stems'
STEM_DIR.mkdir(parents=True, exist_ok=True)

app.mount('/uploads', StaticFiles(directory=UPLOAD_DIR), name='uploads')

SESSIONS: dict[str, dict] = {}


def _session_factory():
    """Return the SQLAlchemy session factory when the store is available."""
    if not STORE_AVAILABLE:
        raise RuntimeError('Persistence store is not available.')
    return _db_get_session_factory()


def _store_session(session: dict) -> None:
    """Best-effort durable persistence; never raise into request handlers."""
    if STORE_AVAILABLE:
        try:
            _db_store.save_session(session, session_factory=_session_factory())
        except Exception as exc:  # pragma: no cover - best-effort durability
            logger.warning('Failed to persist session %s: %s', session.get('file_id'), exc)


def _store_artifact(artifact: dict) -> None:
    """Best-effort artifact registration; never raise into request handlers."""
    if STORE_AVAILABLE:
        try:
            _db_store.save_artifact(artifact, session_factory=_session_factory())
        except Exception as exc:  # pragma: no cover - best-effort durability
            logger.warning('Failed to persist artifact %s: %s', artifact.get('name'), exc)


def _resolve_session(file_id: str) -> dict | None:
    """Resolve a session from the in-memory dict first, then the durable store.

    ``SESSIONS`` is the authoritative cache within a process: every mutation
    writes to it directly, so an entry present here is at least as fresh as the
    store (a store write may have failed and been logged as a WARNING). The store
    is consulted only on a cache miss — exactly the process-restart path, where
    the store is the only surviving source of truth — and the result is seeded
    back into ``SESSIONS`` so every existing helper and test that reads
    ``main.SESSIONS`` directly keeps working unchanged.
    """
    cached = SESSIONS.get(file_id)
    if cached is not None:
        return cached
    if STORE_AVAILABLE:
        try:
            stored = _db_store.get_session(file_id, session_factory=_session_factory())
            if stored is not None:
                SESSIONS[file_id] = stored
                return stored
        except Exception as exc:  # pragma: no cover - store availability guard
            logger.warning('Failed to resolve session %s from store: %s', file_id, exc)
    return SESSIONS.get(file_id)


def _mirror_file(
    local_path: Path,
    object_key: str,
    content_type: str | None,
    local_url: str,
) -> dict:
    """Mirror a local file into the active object-storage backend (best-effort)."""
    if STORE_AVAILABLE and _storage is not None:
        try:
            return _storage.mirror_file(
                local_path=local_path,
                object_key=object_key,
                content_type=content_type,
                local_url=local_url,
            )
        except Exception as exc:  # pragma: no cover - storage availability guard
            logger.warning('Object-storage mirror failed for %s, falling back to local: %s', object_key, exc)
    return {'url': local_url, 'storage_backend': 'local', 'key': None}

ACCEPTED_TYPES = {'audio/wav', 'audio/x-wav', 'audio/mpeg', 'audio/mp3'}
ACCEPTED_EXTENSIONS = {'.wav', '.mp3'}


def get_file_extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def is_content_type_extension_compatible(content_type: str, extension: str) -> bool:
    return (
        extension == '.wav' and content_type in {'audio/wav', 'audio/x-wav'}
    ) or (
        extension == '.mp3' and content_type in {'audio/mpeg', 'audio/mp3'}
    )


async def validate_audio_header(file: UploadFile, extension: str) -> None:
    header = await file.read(1024)
    await file.seek(0)

    if extension == '.wav':
        if len(header) < 12 or header[:4] != b'RIFF' or header[8:12] != b'WAVE':
            raise ValueError('WAV header is invalid or the file is corrupt.')
    elif extension == '.mp3':
        if not (
            header.startswith(b'ID3')
            or (len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xF0) == 0xF0)
        ):
            raise ValueError('MP3 header is invalid or the file is corrupt.')
    else:
        raise ValueError('Unsupported audio extension.')


def error_response(
    error_code: str,
    message: str,
    detail: str | None = None,
    stage: str | None = None,
    next_action: str | None = None,
    workflow_stages: list[WorkflowStageStatus] | None = None,
    status_code: int = 400,
) -> JSONResponse:
    response = UploadErrorResponse(
        error_code=error_code,
        message=message,
        detail=detail,
        stage=stage,
        next_action=next_action,
        workflow_stages=workflow_stages,
    )
    return JSONResponse(status_code=status_code, content=response.model_dump())


def build_workflow_stages(analysis_status: str, analysis_message: str) -> list[WorkflowStageStatus]:
    return [
        WorkflowStageStatus(
            stage='upload',
            status='completed',
            message='Upload completed successfully.',
        ),
        WorkflowStageStatus(
            stage='analysis',
            status=analysis_status,  # type: ignore[arg-type]
            message=analysis_message,
        ),
    ]


def build_analyze_response(file_id: str, analysis: AnalysisMetadata) -> dict:
    workflow_status = analysis.status if analysis.status in {'active', 'failed'} else 'completed'
    workflow_message = analysis.message or 'Analysis completed successfully.'
    if analysis.status == 'failed':
        workflow_message = analysis.message or 'Analysis failed.'

    return AnalyzeResponse(
        file_id=file_id,
        analysis=analysis,
        workflow_stages=build_workflow_stages(workflow_status, workflow_message),
    ).model_dump()


def run_analysis_task(file_id: str, file_path: str) -> dict:
    """Execute analysis via Celery when available, otherwise run in-process.

    Celery dispatch is gated on the broker being reachable so a downed/absent
    Redis falls back to in-process execution immediately rather than blocking
    in kombu's reconnect loop.
    """
    if analyze_audio_task is not None and broker_reachable():
        try:
            async_result = analyze_audio_task.delay(file_id, file_path)
            return async_result.get(timeout=30)
        except Exception:
            pass
    return run_worker_analysis(file_id, file_path)


def mime_for_extension(ext: str | None) -> str:
    ext = (ext or '').lower()
    if ext == 'wav':
        return 'audio/wav'
    if ext == 'mp3':
        return 'audio/mpeg'
    return 'audio/octet-stream'


def build_stage_dicts(
    analysis_status: str,
    analysis_message: str,
    separation_status: str | None = None,
    separation_message: str | None = None,
    separation_next_action: str | None = None,
) -> list[dict]:
    """Build the serialized workflow stage list for a session or response."""
    stages: list[dict] = [
        {'stage': 'upload', 'status': 'completed', 'message': 'Upload completed successfully.'},
        {'stage': 'analysis', 'status': analysis_status, 'message': analysis_message},
    ]
    if separation_status is not None:
        stage: dict = {
            'stage': 'stem_separation',
            'status': separation_status,
            'message': separation_message,
        }
        if separation_next_action:
            stage['next_action'] = separation_next_action
        stages.append(stage)
    return stages


def workflow_stage_models(stages: list[dict]) -> list[WorkflowStageStatus]:
    return [WorkflowStageStatus(**stage) for stage in stages]


def build_separation_response(file_id: str, stems: StemsMetadata) -> dict:
    """Build the separation response payload, preserving the upload/analysis stages."""
    separation_status = stems.status if stems.status in {'active', 'failed'} else 'completed'
    separation_message = stems.message or 'Stem separation completed successfully.'
    if stems.status == 'failed':
        separation_message = stems.message or 'Stem separation failed.'

    analysis = (SESSIONS.get(file_id) or {}).get('analysis') or {}
    analysis_status = analysis.get('status', 'completed')
    analysis_message = analysis.get('message') or 'Analysis completed successfully.'

    workflow_stages = build_stage_dicts(
        analysis_status,
        analysis_message,
        separation_status,
        separation_message,
        stems.next_action,
    )
    return SeparateResponse(
        file_id=file_id,
        stems=stems,
        workflow_stages=workflow_stage_models(workflow_stages),
    ).model_dump()


def run_separation_task(file_id: str, file_path: str, stems_dir) -> dict:
    """Execute separation via Celery when available, otherwise run in-process.

    Gated on the broker being reachable for the same reason as
    ``run_analysis_task`` (fast in-process fallback when Redis is down).
    """
    if separate_stems_task is not None and broker_reachable():
        try:
            async_result = separate_stems_task.delay(file_id, file_path, str(stems_dir))
            return async_result.get(timeout=30)
        except Exception:
            pass
    return run_worker_separation(file_id, file_path, stems_dir)


@app.post('/api/upload')
async def upload_audio(file: UploadFile = File(...)):
    extension = get_file_extension(file.filename)
    if file.content_type not in ACCEPTED_TYPES or extension not in ACCEPTED_EXTENSIONS:
        return error_response(
            'unsupported_audio_format',
            'Unsupported file type. Only WAV and MP3 are accepted.',
            f'Content type {file.content_type} and extension {extension} are not both supported.',
            stage='upload',
            next_action='Choose a WAV or MP3 file and try again.',
            workflow_stages=[
                WorkflowStageStatus(
                    stage='upload',
                    status='failed',
                    message='Upload failed because the selected file type is unsupported.',
                    next_action='Choose a WAV or MP3 file and try again.',
                )
            ],
        )

    if not is_content_type_extension_compatible(file.content_type, extension):
        return error_response(
            'mimetype_extension_mismatch',
            'Unsupported audio file type.',
            f'Expected file extension {extension} to match content type {file.content_type}.',
            stage='upload',
            next_action='Ensure the selected file extension matches the file type and retry.',
            workflow_stages=[
                WorkflowStageStatus(
                    stage='upload',
                    status='failed',
                    message='Upload failed because the MIME type did not match the file extension.',
                    next_action='Ensure the selected file extension matches the file type and retry.',
                )
            ],
        )

    try:
        await validate_audio_header(file, extension)
    except ValueError as exc:
        return error_response(
            'corrupt_audio',
            'Uploaded audio appears to be corrupt or invalid.',
            str(exc),
            stage='upload',
            next_action='Try another WAV or MP3 file or export the source again.',
            workflow_stages=[
                WorkflowStageStatus(
                    stage='upload',
                    status='failed',
                    message='Upload failed because the audio file did not validate.',
                    next_action='Try another WAV or MP3 file or export the source again.',
                )
            ],
        )

    file_id = str(uuid.uuid4())
    filename = f"{file_id}-{Path(file.filename).name}"
    destination = UPLOAD_DIR / filename

    with destination.open('wb') as buffer:
        while content := await file.read(1024 * 1024):
            buffer.write(content)

    local_artifact_url = f"/uploads/{destination.name}"
    mirrored = _mirror_file(
        local_path=destination,
        object_key=f"raw/{file_id}/{destination.name}",
        content_type=file.content_type,
        local_url=local_artifact_url,
    )
    artifact_url = mirrored['url']
    SESSIONS[file_id] = {
        'file_id': file_id,
        'filename': destination.name,
        'content_type': file.content_type,
        'size': destination.stat().st_size,
        'artifact_url': artifact_url,
        'analysis': None,
        'workflow_stages': [
            {
                'stage': 'upload',
                'status': 'completed',
                'message': 'Upload completed successfully.',
            },
            {
                'stage': 'analysis',
                'status': 'pending',
                'message': 'Analysis has not started yet.',
            },
        ],
        'created_at': datetime.now(timezone.utc).isoformat(),
    }
    _store_artifact({
        'file_id': file_id,
        'name': destination.name,
        'url': artifact_url,
        'kind': 'raw_audio',
        'storage_backend': mirrored['storage_backend'],
        'key': mirrored['key'],
        'size': destination.stat().st_size,
        'format': extension.lstrip('.'),
        'mime_type': file.content_type,
    })
    _store_session(SESSIONS[file_id])
    response = UploadResponse(
        file_id=file_id,
        filename=destination.name,
        content_type=file.content_type,
        size=destination.stat().st_size,
        artifact_url=artifact_url,
        message='Upload received',
        workflow_stages=[
            WorkflowStageStatus(
                stage='upload',
                status='completed',
                message='Upload completed successfully.',
            ),
            WorkflowStageStatus(
                stage='analysis',
                status='pending',
                message='Analysis has not started yet.',
            ),
        ],
    )
    return JSONResponse(response.model_dump())


@app.get('/api/session/{file_id}')
async def get_session(file_id: str):
    session = _resolve_session(file_id)
    if not session:
        return JSONResponse(status_code=404, content={'message': 'Session not found.'})
    return JSONResponse(session)


@app.post('/api/analyze', response_model=AnalyzeResponse)
async def analyze_audio(payload: AnalyzeRequest):
    session = _resolve_session(payload.file_id)
    if not session:
        return JSONResponse(
            status_code=404,
            content=AnalyzeErrorResponse(
                error_code='analysis_session_not_found',
                message='Analysis session was not found.',
                detail='No upload session exists for the supplied file_id.',
                stage='analysis',
                next_action='Upload the audio file again and try analysis.',
                workflow_stages=[
                    WorkflowStageStatus(
                        stage='analysis',
                        status='failed',
                        message='Analysis could not start because the session was not found.',
                        next_action='Upload the audio file again and try analysis.',
                    )
                ],
            ).model_dump(),
        )

    existing_analysis = session.get('analysis')
    if existing_analysis and existing_analysis.get('status') == 'completed':
        return JSONResponse(
            build_analyze_response(payload.file_id, AnalysisMetadata.model_validate(existing_analysis))
        )

    task_id = str(uuid.uuid4())
    active_analysis = AnalysisMetadata(
        status='active',
        message='Analyzing audio metadata.',
        task_id=task_id,
    )
    session['analysis'] = active_analysis.model_dump()
    session['workflow_stages'] = [
        {'stage': 'upload', 'status': 'completed', 'message': 'Upload completed successfully.'},
        {'stage': 'analysis', 'status': 'active', 'message': 'Analyzing audio metadata.'},
    ]

    file_path = UPLOAD_DIR / session['filename']
    if not file_path.exists():
        failed_analysis = AnalysisMetadata(
            status='failed',
            task_id=task_id,
            message='Analysis failed because the uploaded artifact could not be found.',
            next_action='Upload the audio file again and retry analysis.',
        )
        session['analysis'] = failed_analysis.model_dump()
        session['workflow_stages'] = [
            {'stage': 'upload', 'status': 'completed', 'message': 'Upload completed successfully.'},
            {
                'stage': 'analysis',
                'status': 'failed',
                'message': failed_analysis.message,
                'next_action': failed_analysis.next_action,
            },
        ]
        _store_session(session)
        return JSONResponse(
            status_code=422,
            content=AnalyzeErrorResponse(
                error_code='analysis_artifact_missing',
                message=failed_analysis.message or 'Analysis artifact missing.',
                detail=f'Expected artifact at {file_path}.',
                stage='analysis',
                next_action=failed_analysis.next_action,
                workflow_stages=build_workflow_stages('failed', failed_analysis.message or 'Analysis failed.'),
            ).model_dump(),
        )

    try:
        worker_result = run_analysis_task(payload.file_id, str(file_path))
    except Exception as exc:
        failed_analysis = AnalysisMetadata(
            status='failed',
            task_id=task_id,
            message='Analysis failed while processing the uploaded audio.',
            next_action='Retry analysis or upload a different WAV or MP3 file.',
        )
        session['analysis'] = failed_analysis.model_dump()
        session['workflow_stages'] = [
            {'stage': 'upload', 'status': 'completed', 'message': 'Upload completed successfully.'},
            {
                'stage': 'analysis',
                'status': 'failed',
                'message': failed_analysis.message,
                'next_action': failed_analysis.next_action,
            },
        ]
        _store_session(session)
        return JSONResponse(
            status_code=500,
            content=AnalyzeErrorResponse(
                error_code='analysis_processing_failed',
                message=failed_analysis.message or 'Analysis failed.',
                detail=str(exc),
                stage='analysis',
                next_action=failed_analysis.next_action,
                workflow_stages=build_workflow_stages('failed', failed_analysis.message or 'Analysis failed.'),
            ).model_dump(),
        )

    # Real analysis (Story 2.4) reports an honest failure through the worker
    # result instead of fabricating metadata. Surface it (never "completed").
    if worker_result.get('status') == 'failed':
        message = worker_result.get('message') or 'Analysis failed while processing the uploaded audio.'
        next_action = worker_result.get('next_action') or 'Retry analysis or upload a different WAV or MP3 file.'
        failed_analysis = AnalysisMetadata(
            status='failed',
            task_id=task_id,
            message=message,
            next_action=next_action,
        )
        session['analysis'] = failed_analysis.model_dump()
        session['workflow_stages'] = [
            {'stage': 'upload', 'status': 'completed', 'message': 'Upload completed successfully.'},
            {'stage': 'analysis', 'status': 'failed', 'message': message, 'next_action': next_action},
        ]
        _store_session(session)
        return JSONResponse(
            status_code=422,
            content=AnalyzeErrorResponse(
                error_code='analysis_processing_failed',
                message=message,
                detail='Real analysis could not be computed from the uploaded audio.',
                stage='analysis',
                next_action=next_action,
                workflow_stages=build_workflow_stages('failed', message),
            ).model_dump(),
        )

    completed_analysis = AnalysisMetadata(
        status='completed',
        bpm=worker_result.get('bpm'),
        key=worker_result.get('key'),
        structure=worker_result.get('structure'),
        duration=worker_result.get('duration'),
        waveform_url=worker_result.get('waveform_url'),
        task_id=task_id,
        message='Analysis completed successfully.',
        analyzed_at=worker_result.get('analyzed_at') or datetime.now(timezone.utc).isoformat(),
    )
    session['analysis'] = completed_analysis.model_dump()
    session['workflow_stages'] = [
        {'stage': 'upload', 'status': 'completed', 'message': 'Upload completed successfully.'},
        {'stage': 'analysis', 'status': 'completed', 'message': 'Analysis completed successfully.'},
    ]
    _store_session(session)

    return JSONResponse(build_analyze_response(payload.file_id, completed_analysis))

@app.post('/api/separate', response_model=SeparateResponse)
async def separate_audio(payload: SeparateRequest):
    session = _resolve_session(payload.file_id)
    if not session:
        stages = build_stage_dicts(
            'pending',
            'Analysis has not started yet.',
            'failed',
            'Separation could not start because the session was not found.',
            'Upload the audio file again and try separation.',
        )
        return JSONResponse(
            status_code=404,
            content=SeparateErrorResponse(
                error_code='separation_session_not_found',
                message='Separation session was not found.',
                detail='No upload session exists for the supplied file_id.',
                stage='stem_separation',
                next_action='Upload the audio file again and try separation.',
                workflow_stages=workflow_stage_models(stages),
            ).model_dump(),
        )

    existing_stems = session.get('stems')
    if existing_stems and existing_stems.get('status') == 'completed':
        return JSONResponse(build_separation_response(payload.file_id, StemsMetadata.model_validate(existing_stems)))

    analysis = session.get('analysis') or {}
    analysis_status = analysis.get('status', 'pending')
    if analysis_status == 'completed':
        analysis_message = analysis.get('message') or 'Analysis completed successfully.'
    else:
        analysis_message = analysis.get('message') or 'Analysis has not been completed yet.'

    if analysis_status != 'completed':
        separation_error = 'Stem separation cannot start because analysis is not complete.'
        stages = build_stage_dicts(
            analysis_status,
            analysis_message,
            'failed',
            separation_error,
            'Run audio analysis first, then retry stem separation.',
        )
        return JSONResponse(
            status_code=422,
            content=SeparateErrorResponse(
                error_code='separation_analysis_not_complete',
                message=separation_error,
                detail='Analysis must be completed before separating stems.',
                stage='stem_separation',
                next_action='Run audio analysis first, then retry stem separation.',
                workflow_stages=workflow_stage_models(stages),
            ).model_dump(),
        )

    task_id = str(uuid.uuid4())
    active_stems = StemsMetadata(status='active', message='Separating audio into stems.', task_id=task_id)
    session['stems'] = active_stems.model_dump()
    session['workflow_stages'] = build_stage_dicts(analysis_status, analysis_message, 'active', 'Separating audio into stems.')

    file_path = UPLOAD_DIR / session['filename']
    if not file_path.exists():
        failed_stems = StemsMetadata(
            status='failed',
            task_id=task_id,
            message='Stem separation failed because the uploaded artifact could not be found.',
            next_action='Upload the audio file again and retry separation.',
        )
        session['stems'] = failed_stems.model_dump()
        stages = build_stage_dicts(analysis_status, analysis_message, 'failed', failed_stems.message, failed_stems.next_action)
        session['workflow_stages'] = stages
        return JSONResponse(
            status_code=422,
            content=SeparateErrorResponse(
                error_code='separation_artifact_missing',
                message=failed_stems.message or 'Separation artifact missing.',
                detail=f'Expected artifact at {file_path}.',
                stage='stem_separation',
                next_action=failed_stems.next_action,
                workflow_stages=workflow_stage_models(stages),
            ).model_dump(),
        )

    stems_dir = STEM_DIR / session['file_id']
    try:
        worker_result = run_separation_task(session['file_id'], str(file_path), stems_dir)
    except Exception as exc:
        failed_stems = StemsMetadata(
            status='failed',
            task_id=task_id,
            message='Stem separation failed while processing the uploaded audio.',
            next_action='Retry separation or upload a different WAV or MP3 file.',
        )
        session['stems'] = failed_stems.model_dump()
        stages = build_stage_dicts(analysis_status, analysis_message, 'failed', failed_stems.message, failed_stems.next_action)
        session['workflow_stages'] = stages
        return JSONResponse(
            status_code=500,
            content=SeparateErrorResponse(
                error_code='separation_processing_failed',
                message=failed_stems.message or 'Stem separation failed.',
                detail=str(exc),
                stage='stem_separation',
                next_action=failed_stems.next_action,
                workflow_stages=workflow_stage_models(stages),
            ).model_dump(),
        )

    # Real separation (Story 2.4) reports an honest failure through the worker
    # result instead of fabricating byte-identical fake stems. Surface it.
    if worker_result.get('status') == 'failed':
        message = worker_result.get('message') or 'Stem separation failed while processing the uploaded audio.'
        next_action = worker_result.get('next_action') or 'Retry separation or upload a different WAV or MP3 file.'
        failed_stems = StemsMetadata(
            status='failed',
            task_id=task_id,
            message=message,
            next_action=next_action,
        )
        session['stems'] = failed_stems.model_dump()
        stages = build_stage_dicts(analysis_status, analysis_message, 'failed', message, next_action)
        session['workflow_stages'] = stages
        _store_session(session)
        return JSONResponse(
            status_code=422,
            content=SeparateErrorResponse(
                error_code='separation_processing_failed',
                message=message,
                detail='Real stem separation could not produce distinct stems for the uploaded audio.',
                stage='stem_separation',
                next_action=next_action,
                workflow_stages=workflow_stage_models(stages),
            ).model_dump(),
        )

    stem_artifacts = []
    for stem in worker_result['stems']:
        stem_local_url = f"/uploads/stems/{session['file_id']}/{stem['filename']}"
        mirrored = _mirror_file(
            local_path=stems_dir / stem['filename'],
            object_key=f"stems/{session['file_id']}/{stem['filename']}",
            content_type=mime_for_extension(stem.get('format')),
            local_url=stem_local_url,
        )

        _store_artifact({
            'file_id': session['file_id'],
            'name': stem['filename'],
            'url': mirrored['url'],
            'kind': 'stem',
            'storage_backend': mirrored['storage_backend'],
            'key': mirrored['key'],
            'size': stem.get('size'),
            'format': stem.get('format'),
            'mime_type': mime_for_extension(stem.get('format')),
        })
        stem_artifacts.append(
            StemArtifact(
                name=stem['name'],
                url=mirrored['url'],
                size=stem.get('size'),
                format=stem.get('format'),
                mime_type=mime_for_extension(stem.get('format')),
                peaks=stem.get('peaks'),
                duration=stem.get('duration'),
            )
        )
    completed_stems = StemsMetadata(
        status='completed',
        stems=stem_artifacts,
        task_id=task_id,
        method=worker_result.get('method'),
        message='Stem separation completed successfully.',
        separated_at=worker_result.get('separated_at') or datetime.now(timezone.utc).isoformat(),
    )
    session['stems'] = completed_stems.model_dump()
    stages = build_stage_dicts(analysis_status, analysis_message, 'completed', 'Stem separation completed successfully.')
    session['workflow_stages'] = stages
    _store_session(session)

    return JSONResponse(build_separation_response(session['file_id'], completed_stems))


def build_regions_response(file_id: str, regions_meta: RegionsMetadata, stages: list[dict]) -> dict:
    """Build the region-save response, echoing the current workflow stages."""
    return RegionsResponse(
        file_id=file_id,
        regions=regions_meta,
        workflow_stages=workflow_stage_models(stages),
    ).model_dump()


def _session_duration_ms(session: dict) -> int | None:
    """Return the session's track duration in ms, or None when unknown."""
    analysis = session.get('analysis') or {}
    duration = analysis.get('duration')
    if duration is None:
        return None
    try:
        return max(0, int(float(duration) * 1000))
    except (TypeError, ValueError):
        return None


@app.post('/api/regions', response_model=RegionsResponse)
async def save_regions(payload: RegionsRequest):
    """Persist the full selected-region set for a session (stateless, sync).

    Replaces any previously stored regions; an empty list clears the selection.
    Regions are plain ``[start_ms, end_ms]`` pairs bounded by the track duration.
    """
    session = _resolve_session(payload.file_id)
    if not session:
        stages = build_stage_dicts('pending', 'Analysis has not started yet.')
        return JSONResponse(
            status_code=404,
            content=RegionsErrorResponse(
                error_code='regions_session_not_found',
                message='Region selection could not be saved because the session was not found.',
                detail='No upload session exists for the supplied file_id.',
                stage='region_selection',
                next_action='Upload the audio file again and re-select the regions you want to transcribe.',
                workflow_stages=workflow_stage_models(stages),
            ).model_dump(),
        )

    stems = session.get('stems') or {}
    analysis = session.get('analysis') or {}
    analysis_status = analysis.get('status', 'pending')
    stems_status = stems.get('status', 'pending')
    if analysis_status == 'completed':
        analysis_message = analysis.get('message') or 'Analysis completed successfully.'
    else:
        analysis_message = analysis.get('message') or 'Analysis has not been completed yet.'
    if stems_status == 'completed':
        stems_message = stems.get('message') or 'Stem separation completed successfully.'
    else:
        stems_message = stems.get('message') or 'Stem separation is not complete yet.'

    if stems_status != 'completed':
        stages = build_stage_dicts(
            analysis_status,
            analysis_message,
            'failed',
            'Region selection cannot be saved before stem separation completes.',
            'Run stem separation first, then select regions for transcription.',
        )
        return JSONResponse(
            status_code=422,
            content=RegionsErrorResponse(
                error_code='regions_stems_not_complete',
                message='Region selection requires completed stems; stem separation has not finished.',
                detail='Stems must be available on the timeline before regions can be selected.',
                stage='region_selection',
                next_action='Wait for stem separation to complete, then select your regions.',
                workflow_stages=workflow_stage_models([s for s in stages if s['stage'] != 'stem_separation']),
            ).model_dump(),
        )

    duration_ms = _session_duration_ms(session)
    for region in payload.regions:
        if region.start_ms < 0 or region.end_ms <= region.start_ms:
            stages = build_stage_dicts(
                analysis_status,
                analysis_message,
                stems_status,
                stems_message,
            )
            return JSONResponse(
                status_code=422,
                content=RegionsErrorResponse(
                    error_code='regions_invalid_region',
                    message='A region must have a positive duration (start_ms < end_ms).',
                    detail=f"Region '{region.id}' has start_ms={region.start_ms}, end_ms={region.end_ms}.",
                    stage='region_selection',
                    next_action='Adjust the region bounds so the end is strictly after the start.',
                    workflow_stages=workflow_stage_models(stages),
                ).model_dump(),
            )
        if duration_ms is not None and region.end_ms > duration_ms:
            stages = build_stage_dicts(
                analysis_status,
                analysis_message,
                stems_status,
                stems_message,
            )
            return JSONResponse(
                status_code=422,
                content=RegionsErrorResponse(
                    error_code='regions_out_of_bounds',
                    message='A region cannot extend beyond the end of the track.',
                    detail=f"Region '{region.id}' ends at {region.end_ms}ms but the track is {duration_ms}ms.",
                    stage='region_selection',
                    next_action='Move or shrink the region so it fits within the track length.',
                    workflow_stages=workflow_stage_models(stages),
                ).model_dump(),
            )

    if payload.regions:
        message = f'Saved {len(payload.regions)} region(s) for transcription.'
    else:
        message = 'All selected regions have been cleared.'

    existing_regions = (session.get('regions') or {}).get('regions') or []
    incoming_regions = [region.model_dump() for region in payload.regions]
    if existing_regions == incoming_regions and session.get('regions'):
        # Identical selection re-save: keep the stored metadata untouched so a
        # retried save is idempotent (stable message + updated_at).
        regions_meta = RegionsMetadata.model_validate(session['regions'])
    else:
        regions_meta = RegionsMetadata(
            status='completed',
            regions=payload.regions,
            message=message,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
    session['regions'] = regions_meta.model_dump()
    stages = build_stage_dicts(analysis_status, analysis_message, stems_status, stems_message)
    session['workflow_stages'] = stages
    _store_session(session)

    return JSONResponse(build_regions_response(payload.file_id, regions_meta, stages))
