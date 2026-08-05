from pydantic import BaseModel

class UploadResponse(BaseModel):
    file_id: str
    filename: str
    content_type: str
    size: int
    artifact_url: str
    message: str


class UploadErrorResponse(BaseModel):
    error_code: str
    message: str
    detail: str | None = None
