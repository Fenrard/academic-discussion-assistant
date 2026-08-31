"""
Shared pipeline toggle schema. The backend is stateless and preset-blind
(CLAUDE.md: "Backend is stateless — receives concrete parameter values,
not preset names") — Flutter's Fast/Balanced/Accurate presets resolve to
one of these on the client before the request is ever sent.
"""

from pydantic import BaseModel, Field

from backend.core.config import settings


class PipelineOptions(BaseModel):
    enable_denoise: bool = False
    enable_vad: bool = True
    enable_diarization: bool = False
    enable_teacher_verification: bool = False
    num_speakers: int | None = None
    beam_size: int = 5
    chunk_duration_seconds: float = Field(
        default=3.0,
        ge=settings.min_chunk_duration_seconds,
        le=settings.max_chunk_duration_seconds,
    )
