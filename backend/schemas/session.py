from datetime import datetime

from pydantic import BaseModel

from backend.schemas.pipeline import PipelineOptions


class SessionSummary(BaseModel):
    id: str
    title: str | None
    status: str
    created_at: datetime
    duration_seconds: float | None


class SessionDetail(SessionSummary):
    consent_confirmed: bool
    pipeline_options: dict
    transcript_text: str
    transcript_segments: list[dict]
    speaker_segments: list[dict]
    keywords: list[str]
    minutes: dict | None
    stage_latencies: dict


class StartSessionMessage(BaseModel):
    """First JSON control frame sent over the WebSocket."""

    type: str = "start"
    title: str | None = None
    options: PipelineOptions = PipelineOptions()
    consent_confirmed: bool = False


class EndSessionMessage(BaseModel):
    """Final JSON control frame sent over the WebSocket."""

    type: str = "end"
