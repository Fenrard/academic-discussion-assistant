"""
ORM model for an enrolled teacher voice (SpeechBrain ECAPA embedding).
Enrollment now runs on the worker tier like transcription (embedding
extraction is model inference — it doesn't belong in the API process
either), so a row starts "pending" and the worker fills in the
embedding once it's done. See backend/worker/tasks.py's
enroll_teacher_task and backend/api/teacher.py's polling GET endpoint.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.db import Base


def _new_teacher_id() -> str:
    return uuid.uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TeacherEnrollment(Base):
    __tablename__ = "teacher_enrollments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_teacher_id)
    owner_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # pending (created, embedding extraction queued) | ready (usable) | failed
    status: Mapped[str] = mapped_column(String, default="pending")
    error_detail: Mapped[str | None] = mapped_column(String, nullable=True)

    # list[float] — ECAPA-TDNN embedding vector (JSON-encoded; small enough not to need a blob
    # column). None until the worker finishes (status="pending"/"failed").
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "error_detail": self.error_detail,
            "created_at": self.created_at.isoformat(),
        }
