"""
ORM model for an app account (a teacher/school-admin logging into the
Flutter client) — distinct from TeacherEnrollment, which is a voice
profile *inside* a recording, not a login. A User owns zero or more
sessions and teacher enrollments.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.db import Base


def _new_user_id() -> str:
    return uuid.uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_user_id)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    def to_dict(self) -> dict:
        return {"id": self.id, "email": self.email, "created_at": self.created_at.isoformat()}
