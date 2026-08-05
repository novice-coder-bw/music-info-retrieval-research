from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import sys
import uuid

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.schemas import UploadResponse

app = FastAPI()
UPLOAD_DIR = Path(__file__).resolve().parent.parent / 'uploads'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app.mount('/uploads', StaticFiles(directory=UPLOAD_DIR), name='uploads')

ACCEPTED_TYPES = {'audio/wav', 'audio/x-wav', 'audio/mpeg', 'audio/mp3'}

@app.post('/api/upload')
async def upload_audio(file: UploadFile = File(...)):
    if file.content_type not in ACCEPTED_TYPES:
        raise HTTPException(status_code=400, detail='Unsupported file type. Only WAV and MP3 are accepted.')

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
    return JSONResponse(response.dict())
