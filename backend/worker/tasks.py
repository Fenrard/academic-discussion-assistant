"""
The two units of work the worker tier actually runs. Both share one
rule: audio arrives as bytes in the task payload (base64, since
Celery's JSON serializer can't carry raw bytes), not a shared file
path — a task can be a totally different machine from the API process
that enqueued it, so nothing here can assume a shared filesystem.

(POST /transcribe's whole-file task is the one exception — see its
docstring. That's a deliberate, documented scaling gap, not an
oversight: base64-embedding a potentially large lecture recording into
a broker message is worse than a shared/network volume for that one
path, and fixing it properly means object storage this sandbox has no
way to stand up or test against.)

backend.services.audio_service (torch/faster-whisper/pyannote/etc.) is
imported lazily, inside each function that needs it, not at module top
— backend/api/transcribe.py and api/teacher.py import THIS module to
get .delay()-able task objects (see that file's docstring for why
that's the right call over celery_app.send_task()), and a top-level
`import audio_service` here would drag every one of those heavy
libraries into the API process just to construct a task signature.
session_service is fine to import eagerly — its own dependency chain
(keyword/minutes/glossary services) is lightweight.
"""

import base64
from pathlib import Path

from backend.core.logging import get_logger
from backend.core.pubsub import publish_sync
from backend.database.db import SessionLocal
from backend.models.session import SessionRecord
from backend.schemas.pipeline import PipelineOptions
from backend.services import session_service
from backend.utils.audio_io import cleanup_temp_files, write_temp_audio
from backend.worker.celery_app import celery_app

_logger = get_logger("scaitale.worker.tasks")


def _run_pipeline_for_chunk(audio_path: Path, options: PipelineOptions, enrolled_teachers: list[tuple[str, list]]) -> dict:
    from backend.services import audio_service
    from backend.worker.celery_app import get_worker_models

    models = get_worker_models()
    return audio_service.run_pipeline(
        audio_path,
        models,
        enable_denoise=options.enable_denoise,
        enable_vad=options.enable_vad,
        enable_diarization=options.enable_diarization,
        enable_teacher_verification=options.enable_teacher_verification,
        num_speakers=options.num_speakers,
        beam_size=options.beam_size,
        enrolled_teachers=enrolled_teachers,
    )


@celery_app.task(name="transcribe_chunk", bind=True, max_retries=0)
def transcribe_chunk_task(
    self, session_id: str, chunk_index: int, audio_b64: str, options_dict: dict, enrolled_teachers: list
) -> None:
    """
    One WS streaming chunk. Persists its result, recomputes the
    session's live transcript, and publishes the outcome (success or
    failure) to session:{id}:results for the WS handler to forward —
    see backend/api/transcribe.py for the receive/listen split this
    feeds into, and session_service.materialize_transcript() for why a
    chunk landing out of order doesn't corrupt the visible transcript.
    """
    channel = f"session:{session_id}:results"
    options = PipelineOptions(**options_dict)
    enrolled = [(name, embedding) for name, embedding in enrolled_teachers]
    # temp_path starts None and write_temp_audio() moves inside the try: a
    # malformed base64 payload or a disk-write failure used to raise here,
    # *before* any try block existed, so no "chunk_result"/"error" message
    # was ever published — the WS handler's state["completed"] would never
    # catch up to state["enqueued"], and the socket would hang open forever
    # instead of finalizing once the client sent "end".
    temp_path = None
    db = SessionLocal()
    try:
        temp_path = write_temp_audio(base64.b64decode(audio_b64))
        result = _run_pipeline_for_chunk(temp_path, options, enrolled)

        session = db.get(SessionRecord, session_id)
        if session is None:
            publish_sync(channel, {"type": "error", "chunk_index": chunk_index, "detail": "Session no longer exists."})
            return

        session = session_service.append_chunk_result(db, session, chunk_index, result)
        publish_sync(channel, {
            "type": "chunk_result",
            "chunk_index": chunk_index,
            "text": result["text"],
            "language": result["language"],
            "whisper_segments": result["whisper_segments"],
            "speaker_segments": result.get("speaker_segments", []),
            "transcript_so_far": session.transcript_text,
        })
    except Exception as error:  # noqa: BLE001 — deliberately broad: this is the task's own error boundary
        # Logged, not just published: a chunk failure only reaches the pubsub
        # channel while a client is still connected to see it. Without this,
        # a session where every chunk happens to fail (e.g. a misconfigured
        # worker) still finalizes as "completed" with an empty transcript —
        # indistinguishable from a genuinely silent session — with no record
        # anywhere that the pipeline itself was broken. This at least makes
        # it visible in the worker's own logs.
        _logger.error(f"transcribe_chunk_task failed for session={session_id} chunk={chunk_index}: {error}")
        publish_sync(channel, {"type": "error", "chunk_index": chunk_index, "detail": str(error)})
    finally:
        db.close()
        cleanup_temp_files(temp_path)


@celery_app.task(name="transcribe_file", bind=True, max_retries=0)
def transcribe_file_task(self, session_id: str, audio_path_str: str, options_dict: dict, enrolled_teachers: list) -> None:
    """
    POST /transcribe's whole-file path. Takes a filesystem path, not
    base64 bytes — a full lecture recording is too large to comfortably
    embed in a broker message. This assumes the API and worker share
    that path (co-located processes, or a shared/network volume in a
    real multi-host deployment) — the properly distributed fix is
    object storage (S3-compatible), left as a documented follow-up
    since it needs real infra this sandbox can't stand up or verify.
    """
    options = PipelineOptions(**options_dict)
    enrolled = [(name, embedding) for name, embedding in enrolled_teachers]
    audio_path = Path(audio_path_str)

    db = SessionLocal()
    try:
        session = db.get(SessionRecord, session_id)
        if session is None:
            return

        result = _run_pipeline_for_chunk(audio_path, options, enrolled)
        session = session_service.append_chunk_result(db, session, 0, result)
        session_service.finalize_session(db, session)
    except Exception:
        session = db.get(SessionRecord, session_id)
        if session is not None:
            session.status = "failed"
            db.add(session)
            db.commit()
        raise
    finally:
        db.close()
        cleanup_temp_files(audio_path)


@celery_app.task(name="enroll_teacher", bind=True, max_retries=0)
def enroll_teacher_task(self, teacher_id: str, audio_b64: str) -> None:
    """
    Teacher enrollment is also model inference (a SpeechBrain embedding
    extraction) — it doesn't belong in the API process any more than
    Whisper transcription does, so it runs here too. The row already
    exists with status="pending" (created synchronously in
    api/teacher.py so the client gets an id back immediately); this
    fills in the embedding or records the failure.
    """
    from backend.services.audio_service import ingest_audio, load_waveform
    from backend.services.teacher_verification_service import extract_embedding
    from backend.worker.celery_app import get_worker_models

    # Both start None, and write_temp_audio() moves inside the try — same
    # reasoning as transcribe_chunk_task: a decode/write failure used to
    # raise before any try block existed, so fail_teacher_enrollment() was
    # never reached and the row stayed "pending" forever with no way for
    # the client's polling to ever see a terminal state.
    temp_path = None
    standardized_path = None
    db = SessionLocal()
    try:
        temp_path = write_temp_audio(base64.b64decode(audio_b64))
        models = get_worker_models()
        if models.teacher_verification_model is None:
            session_service.fail_teacher_enrollment(
                db, teacher_id, "Teacher verification model is not loaded (speechbrain missing on the worker)."
            )
            return

        # Same "FFmpeg preprocessing is ALWAYS ON" rule every other audio
        # path follows (CLAUDE.md) -- this was the one entry point that
        # skipped it, going straight to load_waveform() (which hard-requires
        # exactly 16000Hz) instead of standardizing first. An enrollment
        # upload that isn't already precisely 16kHz mono PCM WAV used to
        # fail with an opaque "Expected 16000Hz audio, got Xhz" error
        # instead of being normalized like every other audio path.
        standardized_path = ingest_audio(temp_path, temp_path.with_name(temp_path.stem + "_std.wav"))
        waveform = load_waveform(standardized_path).numpy()
        embedding = extract_embedding(models.teacher_verification_model, waveform)
        session_service.complete_teacher_enrollment(db, teacher_id, embedding)
    except Exception as error:
        session_service.fail_teacher_enrollment(db, teacher_id, str(error))
    finally:
        db.close()
        cleanup_temp_files(temp_path, standardized_path)
