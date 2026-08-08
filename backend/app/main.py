from datetime import datetime, timezone
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import sys
import uuid

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.schemas import (
    AnalyzeErrorResponse,
    AnalyzeRequest,
    AnalyzeResponse,
    AnalysisMetadata,
    UploadResponse,
    UploadErrorResponse,
    WorkflowStageStatus,
)
from workers.tasks import analyze_audio as run_worker_analysis, analyze_audio_task

app = FastAPI()
UPLOAD_DIR = Path(__file__).resolve().parent.parent / 'uploads'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app.mount('/uploads', StaticFiles(directory=UPLOAD_DIR), name='uploads')

SESSIONS: dict[str, dict] = {}

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
    """Execute analysis via Celery when available, otherwise run in-process."""
    if analyze_audio_task is not None:
        try:
            async_result = analyze_audio_task.delay(file_id, file_path)
            return async_result.get(timeout=30)
        except Exception:
            pass
    return run_worker_analysis(file_id, file_path)


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

    artifact_url = f"/uploads/{destination.name}"
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
    session = SESSIONS.get(file_id)
    if not session:
        return JSONResponse(status_code=404, content={'message': 'Session not found.'})
    return JSONResponse(session)


@app.post('/api/analyze', response_model=AnalyzeResponse)
async def analyze_audio(payload: AnalyzeRequest):
    session = SESSIONS.get(payload.file_id)
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

    return JSONResponse(build_analyze_response(payload.file_id, completed_analysis))
