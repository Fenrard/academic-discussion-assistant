"""Structured minutes retrieval + export — Flutter's "Structured minutes view + export" screen. Owner-scoped throughout."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session as DbSession

from backend.api.deps import get_current_user, get_db
from backend.models.user import User
from backend.services import session_service

router = APIRouter(prefix="/sessions/{session_id}/minutes", tags=["minutes"])


def _get_session_or_404(session_id: str, db: DbSession, owner_id: str):
    session = session_service.get_session(db, owner_id, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"No session found with id '{session_id}'.")
    return session


@router.get("")
def get_minutes(session_id: str, db: DbSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    session = _get_session_or_404(session_id, db, current_user.id)
    if session.minutes is None:
        raise HTTPException(status_code=409, detail="Minutes have not been generated yet for this session.")
    return session.minutes


@router.get("/export")
def export_minutes(
    session_id: str,
    format: str = "markdown",
    db: DbSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = _get_session_or_404(session_id, db, current_user.id)
    if session.minutes is None:
        raise HTTPException(status_code=409, detail="Minutes have not been generated yet for this session.")

    if format not in ("markdown", "txt"):
        raise HTTPException(status_code=400, detail="format must be 'markdown' or 'txt'.")

    body = _render_minutes(session.title, session.minutes, as_markdown=(format == "markdown"))
    extension = "md" if format == "markdown" else "txt"
    filename = f"minutes_{session_id}.{extension}"

    return PlainTextResponse(
        content=body,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _render_minutes(title: str | None, minutes: dict, as_markdown: bool) -> str:
    heading = "#" if as_markdown else ""
    bullet = "-" if as_markdown else "  -"
    lines = [f"{heading} Minutes: {title or 'Untitled session'}".strip()]
    lines.append(f"Generated: {minutes['generated_at']}")
    lines.append(f"Duration: {minutes['duration_seconds']}s")
    lines.append(f"Participants: {', '.join(minutes['participants']) or 'Unknown'}")

    # .get() throughout below: sessions finalized before teacher_speech_ratio/
    # teacher_speakers/definitions existed won't have these keys.
    teacher_ratio = minutes.get("teacher_speech_ratio")
    if teacher_ratio:
        teacher_speakers = ", ".join(minutes.get("teacher_speakers", [])) or "unidentified"
        lines.append(f"Teacher speech: {round(teacher_ratio * 100, 1)}% ({teacher_speakers})")

    lines.append(f"Keywords: {', '.join(minutes['keywords']) or 'None'}")
    lines.append("")

    lines.append(f"{heading}# Topics".strip() if as_markdown else "Topics:")
    for topic in minutes["topics"]:
        lines.append(f"{'##' if as_markdown else ''} {topic['label']} [{topic['start']}s - {topic['end']}s]".strip())
        for point in topic["key_points"]:
            lines.append(f"{bullet} {point}")
        lines.append("")

    lines.append(f"{heading}# Definitions".strip() if as_markdown else "Definitions:")
    definitions = minutes.get("definitions", [])
    if definitions:
        for entry in definitions:
            term = f"**{entry['term']}**" if as_markdown else entry["term"]
            lines.append(f"{bullet} {term} — {entry['definition']}")
    else:
        lines.append(f"{bullet} None detected")
    lines.append("")

    lines.append(f"{heading}# Action Items".strip() if as_markdown else "Action Items:")
    if minutes["action_items"]:
        for item in minutes["action_items"]:
            lines.append(f"{bullet} [{item['start']}s] ({item['speaker']}) {item['text']}")
    else:
        lines.append(f"{bullet} None detected")

    return "\n".join(lines)
