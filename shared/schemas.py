from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class StageStatus(str, Enum):
    """Documented stage / task status values used across analysis, stems, and workflow stages."""

    pending = 'pending'
    active = 'active'
    completed = 'completed'
    failed = 'failed'


# Keep Literal form for OpenAPI stability while documenting the enum values.
StageStatusLiteral = Literal['pending', 'active', 'completed', 'failed']


class WorkflowStageStatus(BaseModel):
    stage: str
    status: StageStatusLiteral = Field(
        ...,
        description='One of: pending, active, completed, failed',
        json_schema_extra={'enum': ['pending', 'active', 'completed', 'failed']},
    )
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
    status: StageStatusLiteral = Field(
        ...,
        description='One of: pending, active, completed, failed',
        json_schema_extra={'enum': ['pending', 'active', 'completed', 'failed']},
    )
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
    status: StageStatusLiteral = Field(
        ...,
        description='One of: pending, active, completed, failed',
        json_schema_extra={'enum': ['pending', 'active', 'completed', 'failed']},
    )
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


class SessionResponse(BaseModel):
    """Session payload returned by GET /api/v1/session/{file_id}.

    Field names match the persisted session document; do not rename without a
    coordinated frontend contract update.
    """

    file_id: str
    user_id: str | None = None
    filename: str | None = None
    content_type: str | None = None
    size: int | None = None
    artifact_url: str | None = None
    analysis: AnalysisMetadata | dict[str, Any] | None = None
    stems: StemsMetadata | dict[str, Any] | None = None
    workflow_stages: list[WorkflowStageStatus] | list[dict[str, Any]] | None = None
    created_at: str | None = None


class CompleteUploadResponse(BaseModel):
    """Response from POST /api/v1/uploads/complete (existing field names)."""

    file_id: str
    status: str
    artifact_url: str


class AuthErrorResponse(BaseModel):
    detail: str
