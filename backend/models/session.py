"""
ORM model for one recording session (whole-file POST /transcribe call, or
one WebSocket streaming connection start-to-end). Deliberately
denormalized: transcript segments, speaker segments, keywords, and
minutes are stored as JSON blobs rather than their own tables. A
thesis-prototype session library doesn't need to query across segments
relationally — it needs one row per session it can hand back whole to
Flutter. Revisit if/when real multi-session analytics are needed.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.db import Base


def _new_session_id() -> str:
    return uuid.uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SessionRecord(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_session_id)
    owner_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="in_progress")  # in_progress | completed | failed | interrupted
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Required at session creation (RA 10173 / Data Privacy Act basics) — the API layer
    # refuses to create a session without this set True. Raw audio is never persisted
    # past processing regardless (temp files are cleaned up in api/transcribe.py's
    # finally blocks) — this field records that the recorded party agreed to that
    # processing happening at all, not a retention toggle for audio we don't keep anyway.
    consent_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Pipeline options this session ran with (concrete values, not preset names).
    pipeline_options: Mapped[dict] = mapped_column(JSON, default=dict)

    # dict[str, dict] keyed by chunk_index (as a string — JSON object keys must be
    # strings) -> that chunk's raw pipeline result. The single source of truth for
    # everything below; chunks from a distributed worker pool can complete out of
    # order, so transcript_text/transcript_segments are *derived*, not appended to
    # directly, by materializing this dict in index order — see
    # session_service.materialize_transcript(). Whole-file POST /transcribe just
    # writes one entry at index 0.
    chunk_results: Mapped[dict] = mapped_column(JSON, default=dict)

    # Growing/final transcript text — the longest *contiguous* prefix of chunk_results
    # (by index, starting at 0), recomputed on every chunk completion. Deliberately not
    # "every chunk received so far in arrival order": a live transcript that could
    # briefly show chunk 3's text before chunk 1's would be a confusing UX regression
    # from the single-process version, which of course had no reordering to worry about.
    transcript_text: Mapped[str] = mapped_column(String, default="")

    # list[dict] — merged Whisper + speaker + teacher-verification segments, same
    # contiguous-prefix rule as transcript_text.
    transcript_segments: Mapped[list] = mapped_column(JSON, default=list)

    # list[dict] — raw diarization output (Speaker A/B/C, start, end, duration).
    speaker_segments: Mapped[list] = mapped_column(JSON, default=list)

    # list[str] — TextRank keywords, populated on finalize.
    keywords: Mapped[list] = mapped_column(JSON, default=list)

    # dict — rule-based structured minutes, populated on finalize.
    minutes: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # dict[str, float] — per-stage latency totals across all chunks, for evaluation/latency.py.
    stage_latencies: Mapped[dict] = mapped_column(JSON, default=dict)

    def to_summary_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "duration_seconds": self.duration_seconds,
        }

    def to_detail_dict(self) -> dict:
        return {
            **self.to_summary_dict(),
            "consent_confirmed": self.consent_confirmed,
            "pipeline_options": self.pipeline_options,
            "transcript_text": self.transcript_text,
            "transcript_segments": self.transcript_segments,
            "speaker_segments": self.speaker_segments,
            "keywords": self.keywords,
            "minutes": self.minutes,
            "stage_latencies": self.stage_latencies,
        }
