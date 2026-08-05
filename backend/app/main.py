from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import sys
import uuid

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.schemas import UploadResponse, UploadErrorResponse

app = FastAPI()
UPLOAD_DIR = Path(__file__).resolve().parent.parent / 'uploads'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app.mount('/uploads', StaticFiles(directory=UPLOAD_DIR), name='uploads')

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


def error_response(error_code: str, message: str, detail: str | None = None) -> JSONResponse:
    response = UploadErrorResponse(error_code=error_code, message=message, detail=detail)
    return JSONResponse(status_code=400, content=response.model_dump())


@app.post('/api/upload')
async def upload_audio(file: UploadFile = File(...)):
    extension = get_file_extension(file.filename)
    if file.content_type not in ACCEPTED_TYPES or extension not in ACCEPTED_EXTENSIONS:
        return error_response(
            'unsupported_audio_format',
            'Unsupported file type. Only WAV and MP3 are accepted.',
            f'Content type {file.content_type} and extension {extension} are not both supported.',
        )

    if not is_content_type_extension_compatible(file.content_type, extension):
        return error_response(
            'mimetype_extension_mismatch',
            'Unsupported audio file type.',
            f'Expected file extension {extension} to match content type {file.content_type}.',
        )

    try:
        await validate_audio_header(file, extension)
    except ValueError as exc:
        return error_response(
            'corrupt_audio',
            'Uploaded audio appears to be corrupt or invalid.',
            str(exc),
        )

    file_id = str(uuid.uuid4())
    filename = f"{file_id}-{Path(file.filename).name}"
    destination = UPLOAD_DIR / filename

    with destination.open('wb') as buffer:
        while content := await file.read(1024 * 1024):
            buffer.write(content)

    artifact_url = f"/uploads/{destination.name}"
    response = UploadResponse(
        file_id=file_id,
        filename=destination.name,
        content_type=file.content_type,
        size=destination.stat().st_size,
        artifact_url=artifact_url,
        message='Upload received',
    )
    return JSONResponse(response.model_dump())
