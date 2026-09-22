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


class StemArtifact(BaseModel):
    name: str
    url: str
    size: int | None = None
    format: str | None = None
    mime_type: str | None = None
    # Pre-computed waveform peaks for instant rendering in WaveSurfer
    peaks: list[list[float]] | None = None
    duration: float | None = None


class StemsMetadata(BaseModel):
    status: Literal['pending', 'active', 'completed', 'failed']
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


class TimeRegion(BaseModel):
    """A single selected time region expressed in milliseconds.

    ``start_ms``/``end_ms`` are the non-negative bounds (ms) of the region on
    the shared session timeline. ``id`` is set by the client so the UI can
    reconcile a region set without relying on server-side identity.
    """

    id: str
    start_ms: int
    end_ms: int


class RegionsMetadata(BaseModel):
    """Region-selection state persisted on a session, mirroring analysis/stems."""

    status: Literal['pending', 'active', 'completed', 'failed']
    regions: list[TimeRegion] | None = None
    message: str | None = None
    next_action: str | None = None
    updated_at: str | None = None


class RegionsRequest(BaseModel):
    file_id: str
    regions: list[TimeRegion]


class RegionsResponse(BaseModel):
    file_id: str
    regions: RegionsMetadata
    workflow_stages: list[WorkflowStageStatus] | None = None


class RegionsErrorResponse(BaseModel):
    error_code: str
    message: str
    detail: str | None = None
    stage: str | None = None
    next_action: str | None = None
    workflow_stages: list[WorkflowStageStatus] | None = None
