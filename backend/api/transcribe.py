"""
POST /transcribe — whole-file, now async: enqueues a worker task and
returns 202 immediately; the client polls GET /sessions/{id}. WS
/ws/transcribe — chunks are enqueued on receipt (non-blocking) and
results are forwarded to the client as the worker tier finishes them,
via backend.core.pubsub. Neither route runs pipeline code itself
anymore — that fixes the original blocking-event-loop bug, since the
API process is never doing CPU-bound work in a request handler.

WS auth is a `?token=` query param, not an Authorization header — the
browser/Flutter WebSocket API can't set custom headers on the opening
handshake, so a query param is the standard workaround for WS auth.

Tasks are enqueued via the imported task objects' .delay() — NOT via
celery_app.send_task("name", ...), which turns out not to work for
this app's dev/test/CI setup at all: send_task() ignores
task_always_eager entirely (Celery logs an AlwaysEagerIgnored warning
and actually posts to the broker), so in eager mode nothing would ever
consume it — no separate worker process is running to pull it back off.
.delay() on an imported task object is what actually respects eager
mode. backend/worker/tasks.py keeps its own imports lazy (inside each
task's function body, not at module top) specifically so importing
this module here doesn't drag torch/faster-whisper/pyannote/etc. into
the API process just to construct a task signature — see that file's
docstring for the split this keeps intact.
"""

import asyncio
import base64
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session as DbSession

from backend.api.deps import get_current_user, get_db
from backend.core.config import settings
from backend.core.pubsub import subscribe
from backend.core.rate_limit import limiter
from backend.core.security import get_current_user_from_token_string
from backend.models.user import User
from backend.schemas.pipeline import PipelineOptions
from backend.services import session_service
from backend.utils.audio_io import write_temp_audio
from backend.worker.tasks import transcribe_chunk_task, transcribe_file_task

router = APIRouter(tags=["transcribe"])

_RESULT_POLL_INTERVAL_SECONDS = 0.5


def _suffix_from_filename(filename: str | None) -> str:
    """
    Derives the temp-file suffix write_temp_audio() saves an upload under.
    Falls back to ".wav" both when there's no filename/extension at all AND
    when the extension is empty (a filename ending in a bare "." — "." in
    the name but rsplit(...)[-1] yields ""), which used to produce a bogus
    "." suffix that ingest_audio()'s SUPPORTED_EXTENSIONS check would reject
    outright. FFmpeg sniffs actual content on decode regardless of this
    suffix, so a wrong-but-supported fallback never affects correctness —
    it only ever affects whether the upload gets a fair chance at all.
    """
    extension = filename.rsplit(".", 1)[-1] if filename and "." in filename else ""
    return f".{extension}" if extension else ".wav"


@router.post("/transcribe", status_code=202)
@limiter.limit(settings.rate_limit_transcribe)
async def transcribe_file(
    request: Request,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    consent_confirmed: bool = Form(...),
    enable_denoise: bool = Form(False),
    enable_vad: bool = Form(True),
    enable_diarization: bool = Form(False),
    enable_teacher_verification: bool = Form(False),
    num_speakers: int | None = Form(None),
    beam_size: int = Form(5),
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
):
    options = PipelineOptions(
        enable_denoise=enable_denoise,
        enable_vad=enable_vad,
        enable_diarization=enable_diarization,
        enable_teacher_verification=enable_teacher_verification,
        num_speakers=num_speakers,
        beam_size=beam_size,
    )

    try:
        session = session_service.create_session(db, current_user.id, title, options, consent_confirmed)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    suffix = _suffix_from_filename(file.filename)
    temp_path = write_temp_audio(await file.read(), suffix=suffix)

    enrolled_teachers = (
        session_service.get_enrolled_embeddings(db, current_user.id) if enable_teacher_verification else []
    )
    transcribe_file_task.delay(session.id, str(temp_path), options.model_dump(), enrolled_teachers)

    return {"session_id": session.id, "status": "processing"}


@router.websocket("/ws/transcribe")
async def transcribe_stream(websocket: WebSocket, db: DbSession = Depends(get_db)):
    token = websocket.query_params.get("token")
    try:
        current_user = get_current_user_from_token_string(token, db)
    except Exception:
        await websocket.close(code=4401)  # custom app close code: authentication failed
        return

    await websocket.accept()

    session = await _handle_start_message(websocket, db, current_user)
    if session is None:
        return  # _handle_start_message already sent an error and closed

    enrolled_teachers = (
        session_service.get_enrolled_embeddings(db, current_user.id)
        if PipelineOptions(**session.pipeline_options).enable_teacher_verification
        else []
    )

    # Shared, cooperatively-checked state between the two loops below — see
    # backend/core/pubsub.py's docstring for why this is a poll loop, not an
    # async generator wrapped in wait_for.
    state = {"enqueued": 0, "completed": 0, "ending": False, "finalized": False, "disconnected": False}

    async def finalize_and_close():
        if state["finalized"]:
            return
        state["finalized"] = True

        # The `session` object was loaded at connection start, in this API process's own
        # DB session — every chunk since then was persisted by the worker tier through ITS
        # OWN separate DB session (a different process/connection). Without expiring first,
        # SQLAlchemy's identity map would happily hand back the stale object from before any
        # chunk committed, and finalize would run on an empty transcript.
        db.expire_all()
        fresh_session = session_service.get_session(db, current_user.id, session.id)
        finalized_session = session_service.finalize_session(db, fresh_session)
        await websocket.send_json({
            "type": "session_ended",
            "session_id": finalized_session.id,
            "transcript": finalized_session.transcript_text,
            "keywords": finalized_session.keywords,
            "minutes": finalized_session.minutes,
        })
        await websocket.close()

    async def receive_chunks():
        options = PipelineOptions(**session.pipeline_options)
        while True:
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                state["disconnected"] = True
                return

            if "bytes" in message and message["bytes"] is not None:
                chunk_index = state["enqueued"]
                state["enqueued"] += 1
                audio_b64 = base64.b64encode(message["bytes"]).decode("ascii")
                transcribe_chunk_task.delay(
                    session.id, chunk_index, audio_b64, options.model_dump(), enrolled_teachers
                )

            elif "text" in message and message["text"] is not None:
                try:
                    control = json.loads(message["text"])
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "detail": "Control frame was not valid JSON."})
                    continue

                if control.get("type") == "end":
                    state["ending"] = True
                    return
                else:
                    await websocket.send_json({
                        "type": "error",
                        "detail": f"Unknown control message type: {control.get('type')!r}",
                    })

    async def listen_results():
        async with subscribe(f"session:{session.id}:results") as results:
            while True:
                message = await results.get(timeout=_RESULT_POLL_INTERVAL_SECONDS)
                if message is not None:
                    state["completed"] += 1
                    try:
                        await websocket.send_json(message)
                    except Exception:
                        # Client disconnected in the narrow window between us picking up
                        # this result and sending it — the receive loop's own disconnect
                        # check below still ends this loop cleanly either way.
                        state["disconnected"] = True

                if state["disconnected"]:
                    return
                if state["ending"] and state["completed"] >= state["enqueued"]:
                    await finalize_and_close()
                    return

    try:
        await asyncio.gather(receive_chunks(), listen_results())
    except WebSocketDisconnect:
        state["disconnected"] = True
    except Exception as error:
        # e.g. the pub/sub backend (Redis) is unreachable — listen_results()
        # can't even subscribe. Without this the connection just drops with no
        # close frame and the client sees a raw ConnectionClosedError; send one
        # clean error frame and mark the session interrupted like any other
        # mid-session failure.
        state["disconnected"] = True
        try:
            await websocket.send_json({"type": "error", "detail": f"Streaming backend error: {error}"})
            await websocket.close()
        except Exception:
            pass
    finally:
        if state["disconnected"] and session.status == "in_progress":
            session.status = "interrupted"
            db.add(session)
            db.commit()


async def _handle_start_message(websocket: WebSocket, db: DbSession, current_user: User):
    """Reads the mandatory first control frame, creates the session, or sends an error and closes."""
    try:
        message = await websocket.receive()
        if message.get("type") == "websocket.disconnect":
            return None

        control = json.loads(message["text"])
        if control.get("type") != "start":
            raise ValueError("First message must be {\"type\": \"start\", ...}.")

        options = PipelineOptions(**control.get("options", {}))
        session = session_service.create_session(
            db, current_user.id, control.get("title"), options, bool(control.get("consent_confirmed", False))
        )
    except Exception as error:
        try:
            await websocket.send_json({"type": "error", "detail": str(error)})
        finally:
            await websocket.close()
        return None

    await websocket.send_json({"type": "session_started", "session_id": session.id})
    return session
