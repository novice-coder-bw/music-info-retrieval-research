from typing import Literal

from pydantic import BaseModel

class WorkflowStageStatus(BaseModel):
    stage: str
    status: Literal['pending', 'active', 'completed', 'failed']
    message: str | None = None
    next_action: str | None = None

class UploadResponse(BaseModel):
    file_id: str
    filename: str
    content_type: str
    size: int
    artifact_url: str
    message: str
    workflow_stages: list[WorkflowStageStatus] | None = None


class UploadErrorResponse(BaseModel):
    error_code: str
    message: str
    detail: str | None = None
    stage: str | None = None
    next_action: str | None = None
    workflow_stages: list[WorkflowStageStatus] | None = None
