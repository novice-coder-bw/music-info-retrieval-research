from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class StageStatus(str, Enum):
    """Status of a workflow stage, analysis or stem separation.

    - `pending`: queued, not started
    - `active`: running
    - `completed`: finished successfully
    - `failed`: finished with an error; see `message` / `next_action`
    """

    pending = 'pending'
    active = 'active'
    completed = 'completed'
    failed = 'failed'


class HTTPErrorResponse(BaseModel):
    """Error body returned by `HTTPException` (400, 401, 403, 404, 409, 413)."""

    detail: str


class WorkflowStageStatus(BaseModel):
    stage: str
    status: StageStatus
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


class AnalyzeRequest(BaseModel):
    file_id: str
    filename: str | None = None
    artifact_url: str | None = None


class AnalysisMetadata(BaseModel):
    status: StageStatus
    bpm: float | None = None
    key: str | None = None
    structure: list[str] | None = None
    duration: float | None = None
    waveform_url: str | None = None
    task_id: str | None = None
    message: str | None = None
    next_action: str | None = None
    analyzed_at: str | None = None


class AnalyzeResponse(BaseModel):
    file_id: str
    analysis: AnalysisMetadata
    workflow_stages: list[WorkflowStageStatus]


class AnalyzeErrorResponse(BaseModel):
    error_code: str
    message: str
    detail: str | None = None
    stage: str | None = None
    next_action: str | None = None
    workflow_stages: list[WorkflowStageStatus] | None = None


class StemArtifact(BaseModel):
    name: str
    url: str
    size: int | None = None
    format: str | None = None
    mime_type: str | None = None


class StemsMetadata(BaseModel):
    status: StageStatus
    stems: list[StemArtifact] | None = None
    task_id: str | None = None
    method: str | None = None
    message: str | None = None
    next_action: str | None = None
    separated_at: str | None = None


class SeparateRequest(BaseModel):
    file_id: str


class SeparateResponse(BaseModel):
    file_id: str
    stems: StemsMetadata
    workflow_stages: list[WorkflowStageStatus]


class SeparateErrorResponse(BaseModel):
    error_code: str
    message: str
    detail: str | None = None
    stage: str | None = None
    next_action: str | None = None
    workflow_stages: list[WorkflowStageStatus] | None = None


class CompleteUploadResponse(BaseModel):
    file_id: str
    status: Literal['enqueued']
    artifact_url: str


class SessionStemArtifact(StemArtifact):
    """Stem entry as stored on the session; unknown keys are passed through."""

    model_config = ConfigDict(extra='allow')

    filename: str | None = None
    storage_backend: str | None = None
    key: str | None = None


class SessionAnalysis(AnalysisMetadata):
    """Analysis result as stored on the session; unknown keys are passed through."""

    model_config = ConfigDict(extra='allow')

    file_id: str | None = None


class SessionStems(StemsMetadata):
    """Stem separation result as stored on the session; unknown keys are passed through."""

    model_config = ConfigDict(extra='allow')

    file_id: str | None = None
    stems: list[SessionStemArtifact] | None = None


class SessionResponse(BaseModel):
    file_id: str
    user_id: str | None = None
    filename: str | None = None
    content_type: str | None = None
    size: int | None = None
    artifact_url: str | None = None
    analysis: SessionAnalysis | None = None
    stems: SessionStems | None = None
    workflow_stages: list[WorkflowStageStatus] | None = None
    created_at: str | None = None
    updated_at: str | None = None
