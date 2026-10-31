from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import sys
import uuid

from fastapi import Depends, FastAPI, File, HTTPException, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.auth import get_current_user_id  # noqa: E402
from db.engine import get_engine  # noqa: E402
from db import store as db_store  # noqa: E402
from services import storage  # noqa: E402
from shared.schemas import (  # noqa: E402
    AnalysisMetadata,
    AnalyzeErrorResponse,
    AnalyzeRequest,
    AnalyzeResponse,
    SeparateErrorResponse,
    SeparateRequest,
    SeparateResponse,
    StemsMetadata,
    UploadErrorResponse,
    UploadResponse,
    WorkflowStageStatus,
)
from workers.tasks import analyze_audio_task, app as celery_app, separate_stems_task  # noqa: E402

logger = logging.getLogger(__name__)

app = FastAPI(
    title='Music Analysis Platform API',
    description='API for stem separation and audio feature analysis',
    version='1.0.0',
)

# CORS setup
cors_origin_regex = os.environ.get(
    'CORS_ORIGIN_REGEX',
    r'^https:\/\/(.*\.)?(lovable\.app|lovableproject\.com|pages\.dev)(:[0-9]+)?$',
)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=cors_origin_regex,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

MAX_UPLOAD_MB = int(os.environ.get('MAX_UPLOAD_MB', '100'))
ALLOWED_MIME_TYPES = {'audio/wav', 'audio/x-wav', 'audio/mpeg', 'audio/mp3'}


class PresignUploadRequest(BaseModel):
    filename: str
    content_type: str = Field(..., description='audio/wav or audio/mpeg')
    size_bytes: int = Field(..., description='Size of audio in bytes')


class PresignUploadResponse(BaseModel):
    file_id: str
    object_key: str
    upload_url: str
    expires_in: int


class CompleteUploadRequest(BaseModel):
    file_id: str
    object_key: str
    filename: str
    content_type: str
    size_bytes: int


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Health Check ---
@app.get('/health', tags=['Monitoring'])
def health(response: Response):
    """Health check for Postgres, Redis, R2, and Celery worker.

    Returns HTTP 200 if all services pass, or HTTP 503 if any service fails.
    """
    checks = {
        'database': False,
        'redis': False,
        'storage': False,
        'worker': False,
    }

    # 1. Postgres check
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        checks['database'] = True
    except Exception as exc:
        logger.warning('Health check - database failed: %s', exc)

    # 2. Redis check
    try:
        redis_client = celery_app.backend.client
        if redis_client.ping():
            checks['redis'] = True
    except Exception as exc:
        logger.warning('Health check - redis failed: %s', exc)

    # 3. R2 check
    try:
        s3 = storage.get_s3_client()
        settings = storage.get_r2_settings()
        s3.head_bucket(Bucket=settings['bucket'])
        checks['storage'] = True
    except Exception as exc:
        logger.warning('Health check - R2 storage failed: %s', exc)

    # 4. Celery worker ping
    try:
        ping_res = celery_app.control.ping(timeout=1.0)
        if ping_res and len(ping_res) > 0:
            checks['worker'] = True
    except Exception as exc:
        logger.warning('Health check - worker failed: %s', exc)

    all_healthy = all(checks.values())
    if not all_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        'status': 'ok' if all_healthy else 'degraded',
        **checks,
    }


# --- API v1 Uploads ---
@app.post(
    '/api/v1/uploads/presign',
    response_model=PresignUploadResponse,
    tags=['Uploads'],
)
def presign_upload(req: PresignUploadRequest, user_id: str = Depends(get_current_user_id)):
    """Generate a presigned PUT URL for client-direct upload to Cloudflare R2."""
    if req.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Unsupported content type: {req.content_type}. Allowed: audio/wav, audio/mpeg.',
        )
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    if req.size_bytes > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f'File size ({req.size_bytes} bytes) exceeds limit of {MAX_UPLOAD_MB} MB.',
        )

    file_id = str(uuid.uuid4())
    ext = '.mp3' if 'mpeg' in req.content_type or 'mp3' in req.content_type else '.wav'
    object_key = f'uploads/{file_id}/source{ext}'
    upload_url = storage.generate_presigned_put_url(
        object_key=object_key,
        content_type=req.content_type,
        expires_in=3600,
    )

    return PresignUploadResponse(
        file_id=file_id,
        object_key=object_key,
        upload_url=upload_url,
        expires_in=3600,
    )


@app.post(
    '/api/v1/uploads/complete',
    tags=['Uploads'],
)
def complete_upload(req: CompleteUploadRequest, user_id: str = Depends(get_current_user_id)):
    """Complete direct upload: verify R2 object, create session, enqueue analysis."""
    # Verify object exists in R2
    s3 = storage.get_s3_client()
    settings = storage.get_r2_settings()
    try:
        object_info = s3.head_object(Bucket=settings['bucket'], Key=req.object_key)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Uploaded object not found in R2: {exc}',
        ) from exc

    object_size = object_info.get('ContentLength')
    object_type = object_info.get('ContentType')
    if not isinstance(object_size, int) or object_size < 0:
        s3.delete_object(Bucket=settings['bucket'], Key=req.object_key)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid object size.')
    if object_size > MAX_UPLOAD_MB * 1024 * 1024:
        s3.delete_object(Bucket=settings['bucket'], Key=req.object_key)
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=f'File size exceeds {MAX_UPLOAD_MB} MB.')
    if object_type not in ALLOWED_MIME_TYPES:
        s3.delete_object(Bucket=settings['bucket'], Key=req.object_key)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unsupported object content type.')

    artifact_url = storage.get_public_url(req.object_key)
    now_iso = _utcnow_iso()
    session_data = {
        'file_id': req.file_id,
        'user_id': user_id,
        'filename': req.filename,
        'content_type': object_type,
        'size': object_size,
        'artifact_url': artifact_url,
        'analysis': {'status': 'pending'},
        'stems': {'status': 'pending'},
        'workflow_stages': [
            {'stage': 'upload', 'status': 'completed', 'message': 'File uploaded directly to storage.'},
            {'stage': 'analysis', 'status': 'pending', 'message': 'Enqueued for analysis.'},
        ],
        'created_at': now_iso,
    }
    db_store.save_session(session_data)
    db_store.save_artifact({
        'file_id': req.file_id,
        'name': req.filename,
        'url': artifact_url,
        'kind': 'source_audio',
        'storage_backend': 'r2',
        'key': req.object_key,
        'size': object_size,
        'format': Path(req.filename).suffix.lstrip('.') or 'wav',
        'mime_type': object_type,
    })

    # Enqueue analysis task
    analyze_audio_task.delay(req.file_id, artifact_url)

    return {'file_id': req.file_id, 'status': 'enqueued', 'artifact_url': artifact_url}


# --- Multipart Upload (v1 & legacy alias) ---
@app.post(
    '/api/v1/upload',
    response_model=UploadResponse,
    responses={400: {'model': UploadErrorResponse}},
    tags=['Uploads'],
)
@app.post(
    '/api/upload',
    response_model=UploadResponse,
    responses={400: {'model': UploadErrorResponse}},
    deprecated=True,
    tags=['Legacy Aliases'],
)
async def upload_file(file: UploadFile = File(...), user_id: str = Depends(get_current_user_id)):
    """Multipart audio upload handler (saves to R2 and creates session)."""
    if not file.filename:
        return JSONResponse(
            status_code=400,
            content=UploadErrorResponse(
                error_code='upload_missing_filename',
                message='No filename provided',
                next_action='Select a valid audio file to upload',
            ).model_dump(),
        )

    ext = Path(file.filename).suffix.lower()
    if ext not in {'.wav', '.mp3'}:
        return JSONResponse(
            status_code=400,
            content=UploadErrorResponse(
                error_code='upload_invalid_type',
                message=f'Unsupported file format: {ext}. Only WAV and MP3 are supported.',
                next_action='Convert your audio file to WAV or MP3 and try again.',
            ).model_dump(),
        )

    file_id = str(uuid.uuid4())
    object_key = f'uploads/{file_id}/{file.filename}'
    content = await file.read()
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f'File size exceeds {MAX_UPLOAD_MB} MB.',
        )

    s3 = storage.get_s3_client()
    settings = storage.get_r2_settings()
    s3.put_object(
        Bucket=settings['bucket'],
        Key=object_key,
        Body=content,
        ContentType=file.content_type or 'audio/wav',
    )
    artifact_url = storage.get_public_url(object_key)
    now_iso = _utcnow_iso()

    session_data = {
        'file_id': file_id,
        'user_id': user_id,
        'filename': file.filename,
        'content_type': file.content_type or 'audio/wav',
        'size': len(content),
        'artifact_url': artifact_url,
        'analysis': None,
        'stems': None,
        'workflow_stages': [
            {'stage': 'upload', 'status': 'completed', 'message': 'File uploaded.'},
        ],
        'created_at': now_iso,
    }
    db_store.save_session(session_data)
    db_store.save_artifact({
        'file_id': file_id,
        'name': file.filename,
        'url': artifact_url,
        'kind': 'source_audio',
        'storage_backend': 'r2',
        'key': object_key,
        'size': len(content),
        'format': ext.lstrip('.'),
        'mime_type': file.content_type or 'audio/wav',
    })

    workflow_stages = [
        WorkflowStageStatus(stage='upload', status='completed', message='File uploaded.'),
    ]
    return UploadResponse(
        file_id=file_id,
        filename=file.filename,
        content_type=file.content_type or 'audio/wav',
        size=len(content),
        artifact_url=artifact_url,
        message='File uploaded successfully',
        workflow_stages=workflow_stages,
    )


# --- Session Details (v1 & legacy alias) ---
@app.get('/api/v1/session/{file_id}', tags=['Sessions'])
@app.get('/api/session/{file_id}', deprecated=True, tags=['Legacy Aliases'])
def get_session(file_id: str, user_id: str = Depends(get_current_user_id)):
    """Fetch session details. Users can only access sessions they own."""
    session = db_store.get_session(file_id)
    if not session:
        raise HTTPException(status_code=404, detail='Session not found')
    if session.get('user_id') and session.get('user_id') != user_id:
        raise HTTPException(status_code=403, detail='Access forbidden: session belongs to another user')
    return session


# --- Analyze Audio (v1 & legacy alias) ---
@app.post(
    '/api/v1/analyze',
    response_model=AnalyzeResponse,
    responses={400: {'model': AnalyzeErrorResponse}, 404: {'model': AnalyzeErrorResponse}, 422: {'model': AnalyzeErrorResponse}},
    tags=['Analysis'],
)
@app.post(
    '/api/analyze',
    response_model=AnalyzeResponse,
    deprecated=True,
    tags=['Legacy Aliases'],
)
def analyze(req: AnalyzeRequest, user_id: str = Depends(get_current_user_id)):
    """Enqueue audio analysis."""
    session = db_store.get_session(req.file_id)
    if not session:
        return JSONResponse(
            status_code=404,
            content=AnalyzeErrorResponse(
                error_code='analyze_file_not_found',
                message='Session not found',
                stage='analysis',
                next_action='Upload a file first',
            ).model_dump(),
        )
    if session.get('user_id') and session.get('user_id') != user_id:
        raise HTTPException(status_code=403, detail='Access forbidden')

    artifact_url = session.get('artifact_url') or req.artifact_url
    analyze_audio_task.delay(req.file_id, artifact_url)
    analysis = session.get('analysis') or {'status': 'pending'}
    stages = [WorkflowStageStatus(**s) for s in (session.get('workflow_stages') or [])]
    return AnalyzeResponse(
        file_id=req.file_id,
        analysis=AnalysisMetadata(**analysis),
        workflow_stages=stages,
    )


# --- Separate Stems (v1 & legacy alias) ---
@app.post(
    '/api/v1/separate',
    response_model=SeparateResponse,
    responses={400: {'model': SeparateErrorResponse}, 404: {'model': SeparateErrorResponse}, 422: {'model': SeparateErrorResponse}},
    tags=['Separation'],
)
@app.post(
    '/api/separate',
    response_model=SeparateResponse,
    deprecated=True,
    tags=['Legacy Aliases'],
)
def separate(req: SeparateRequest, user_id: str = Depends(get_current_user_id)):
    """Enqueue Demucs stem separation."""
    session = db_store.get_session(req.file_id)
    if not session:
        return JSONResponse(
            status_code=404,
            content=SeparateErrorResponse(
                error_code='separate_file_not_found',
                message='Session not found',
                stage='stem_separation',
                next_action='Upload a file first',
            ).model_dump(),
        )
    if session.get('user_id') and session.get('user_id') != user_id:
        raise HTTPException(status_code=403, detail='Access forbidden')

    artifact_url = session.get('artifact_url')
    if not artifact_url:
        return JSONResponse(
            status_code=422,
            content=SeparateErrorResponse(
                error_code='separate_missing_artifact',
                message='Audio artifact URL missing for session',
                stage='stem_separation',
                next_action='Upload file again',
            ).model_dump(),
        )

    separate_stems_task.delay(req.file_id, artifact_url)
    stems = session.get('stems') or {'status': 'pending', 'stems': []}
    stages = [WorkflowStageStatus(**s) for s in (session.get('workflow_stages') or [])]
    return SeparateResponse(
        file_id=req.file_id,
        stems=StemsMetadata(**stems),
        workflow_stages=stages,
    )
