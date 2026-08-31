"""Session library — Flutter's "Home / session library" and "Transcript view" screens. Owner-scoped throughout."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from backend.api.deps import get_current_user, get_db
from backend.models.user import User
from backend.schemas.session import SessionDetail, SessionSummary
from backend.services import session_service

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionSummary])
def list_sessions(db: DbSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    return [session.to_summary_dict() for session in session_service.list_sessions(db, current_user.id)]


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(session_id: str, db: DbSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    session = session_service.get_session(db, current_user.id, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"No session found with id '{session_id}'.")
    return session.to_detail_dict()


@router.delete("/{session_id}")
def delete_session(session_id: str, db: DbSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Full purge — RA 10173 right-to-deletion basics. Raw audio was already never persisted past processing."""
    deleted = session_service.delete_session(db, current_user.id, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No session found with id '{session_id}'.")
    return {"deleted": True}
