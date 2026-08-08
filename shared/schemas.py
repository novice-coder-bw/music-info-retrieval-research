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


class AnalyzeRequest(BaseModel):
    file_id: str
    filename: str | None = None
    artifact_url: str | None = None


class AnalysisMetadata(BaseModel):
    status: Literal['pending', 'active', 'completed', 'failed']
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
