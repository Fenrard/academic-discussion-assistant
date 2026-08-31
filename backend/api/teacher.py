"""
Teacher voice enrollment — backend side of the Flutter "Teacher voice
enrollment" screen. Embedding extraction is model inference (SpeechBrain),
so like transcription it runs on the worker tier, not in this request
handler — POST /enroll creates a "pending" row and returns immediately;
the client polls GET /teachers/{id} (or GET /teachers) for status
"ready"/"failed". Owner-scoped throughout.
"""

import base64

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session as DbSession

from backend.api.deps import get_current_user, get_db
from backend.core.config import settings
from backend.core.rate_limit import limiter
from backend.models.user import User
from backend.schemas.teacher import TeacherOut
from backend.services import session_service
from backend.worker.tasks import enroll_teacher_task

router = APIRouter(prefix="/teachers", tags=["teacher-verification"])


@router.post("/enroll", response_model=TeacherOut, status_code=202)
@limiter.limit(settings.rate_limit_enroll)
async def enroll_teacher(
    request: Request,
    name: str = Form(...),
    file: UploadFile = File(...),
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    teacher = session_service.create_pending_teacher(db, current_user.id, name)

    audio_b64 = base64.b64encode(await file.read()).decode("ascii")
    enroll_teacher_task.delay(teacher.id, audio_b64)

    return teacher.to_dict()


@router.get("", response_model=list[TeacherOut])
def list_teachers(db: DbSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    return [teacher.to_dict() for teacher in session_service.list_teachers(db, current_user.id)]


@router.get("/{teacher_id}", response_model=TeacherOut)
def get_teacher(teacher_id: str, db: DbSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    teacher = session_service.get_teacher(db, current_user.id, teacher_id)
    if teacher is None:
        raise HTTPException(status_code=404, detail=f"No enrolled teacher found with id '{teacher_id}'.")
    return teacher.to_dict()


@router.delete("/{teacher_id}")
def delete_teacher(teacher_id: str, db: DbSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    deleted = session_service.delete_teacher(db, current_user.id, teacher_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No enrolled teacher found with id '{teacher_id}'.")
    return {"deleted": True}
