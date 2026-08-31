from datetime import datetime

from pydantic import BaseModel


class TeacherOut(BaseModel):
    id: str
    name: str
    status: str  # pending | ready | failed
    error_detail: str | None
    created_at: datetime
