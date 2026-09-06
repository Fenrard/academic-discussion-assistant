"""
Persistence + finalization layer sitting between the API/worker tiers
and audio_service.run_pipeline(). Owns the "Storage" stage in CLAUDE.md's
locked pipeline order, the point where glossary-corrected per-chunk
output becomes session-wide keywords + minutes, and (now that inference
runs on a worker pool that can complete chunks out of order) the
reordering logic that keeps the live transcript coherent regardless.

Every read/write here is owner-scoped — a user only ever sees their own
sessions and teacher enrollments.
"""

from sqlalchemy.orm import Session as DbSession

from backend.models.session import SessionRecord
from backend.models.teacher import TeacherEnrollment
from backend.schemas.pipeline import PipelineOptions
from backend.services.keyword_service import build_weighted_text, extract_keywords
from backend.services.minutes_service import generate_minutes


def create_session(
    db: DbSession, owner_id: str, title: str | None, options: PipelineOptions, consent_confirmed: bool
) -> SessionRecord:
    if not consent_confirmed:
        raise ValueError("consent_confirmed must be true to start a session — see RA 10173 note in session model.")

    session = SessionRecord(
        owner_id=owner_id,
        title=title,
        pipeline_options=options.model_dump(),
        status="in_progress",
        consent_confirmed=consent_confirmed,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def materialize_transcript(chunk_results: dict) -> dict:
    """
    Rebuilds transcript_text/transcript_segments/speaker_segments from
    whatever prefix of chunk_results (keyed by string chunk_index) is
    contiguous starting at "0" — chunks 2 and 3 landing before chunk 1
    (a distributed worker pool completes tasks in whatever order they
    finish) contribute nothing to the visible transcript until chunk 1
    arrives and closes the gap. duration_seconds and stage_latencies
    ARE order-independent (a sum), so those count every completed chunk.
    """
    text_parts, segments, speaker_segments = [], [], []
    index = 0
    while str(index) in chunk_results:
        chunk = chunk_results[str(index)]
        if chunk["text"]:
            text_parts.append(chunk["text"])
        segments.extend(chunk["whisper_segments"])
        speaker_segments.extend(chunk.get("speaker_segments", []))
        index += 1

    total_duration = sum(chunk["audio_duration_seconds"] for chunk in chunk_results.values())

    latencies: dict[str, float] = {}
    for chunk in chunk_results.values():
        for stage, elapsed in chunk.get("stage_latencies", {}).items():
            latencies[stage] = round(latencies.get(stage, 0.0) + elapsed, 4)

    return {
        "transcript_text": " ".join(text_parts).strip(),
        "transcript_segments": segments,
        "speaker_segments": speaker_segments,
        "duration_seconds": round(total_duration, 2),
        "stage_latencies": latencies,
        "contiguous_chunk_count": index,
    }


def append_chunk_result(db: DbSession, session: SessionRecord, chunk_index: int, pipeline_result: dict) -> SessionRecord:
    """
    Records one chunk's raw pipeline output and recomputes the derived
    transcript fields from it.

    Refreshes `session` with a row-level lock (SELECT ... FOR UPDATE, on
    dialects that support it) before reading chunk_results, rather than
    trusting whatever the caller's own db.get() loaded earlier: under a
    real multi-worker pool, two chunks of the same session can finish on
    different worker processes near-simultaneously, each with its own DB
    session that loaded chunk_results before the other's write landed.
    Without a lock, whichever commits last silently overwrites the
    other's chunk (a lost update, no exception raised anywhere) — the
    lock forces the second call to wait for the first transaction to
    commit and release it, then re-read the now-current chunk_results
    before merging its own chunk on top. On SQLite (this project's
    dev/test default), FOR UPDATE isn't part of the dialect's grammar, so
    this is a no-op there — it only takes effect, and only matters, under
    the real Postgres multi-worker deployment where the race is actually
    possible; proven directly in tests/test_session_service.py against a
    real Postgres instance, not just reasoned about.
    """
    db.refresh(session, with_for_update=True)

    chunk_results = dict(session.chunk_results)
    chunk_results[str(chunk_index)] = pipeline_result
    session.chunk_results = chunk_results

    materialized = materialize_transcript(chunk_results)
    session.transcript_text = materialized["transcript_text"]
    session.transcript_segments = materialized["transcript_segments"]
    session.speaker_segments = materialized["speaker_segments"]
    session.duration_seconds = materialized["duration_seconds"]
    session.stage_latencies = materialized["stage_latencies"]

    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def finalize_session(db: DbSession, session: SessionRecord) -> SessionRecord:
    """
    Runs the discourse-level stages that need the *whole* transcript
    (TextRank keywords, then rule-based minutes) and marks the session
    complete. Safe to call on an empty transcript (e.g. a session with
    no detected speech, or one where a chunk never completed and the
    contiguous prefix stopped early) — just yields empty/partial
    keywords/minutes rather than raising.
    """
    # Weighted, not the raw transcript_text — teacher speech counts more toward
    # which keywords surface, when teacher verification was enabled. See
    # build_weighted_text()'s docstring for why this is a no-op otherwise.
    keywords = extract_keywords(build_weighted_text(session.transcript_segments))
    session.keywords = keywords

    if session.transcript_segments:
        session.minutes = generate_minutes(session.transcript_segments, keywords)
    else:
        session.minutes = None

    session.status = "completed"
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_session(db: DbSession, owner_id: str, session_id: str) -> SessionRecord | None:
    return (
        db.query(SessionRecord)
        .filter(SessionRecord.id == session_id, SessionRecord.owner_id == owner_id)
        .first()
    )


def list_sessions(db: DbSession, owner_id: str) -> list[SessionRecord]:
    return (
        db.query(SessionRecord)
        .filter(SessionRecord.owner_id == owner_id)
        .order_by(SessionRecord.created_at.desc())
        .all()
    )


def delete_session(db: DbSession, owner_id: str, session_id: str) -> bool:
    session = get_session(db, owner_id, session_id)
    if session is None:
        return False
    db.delete(session)
    db.commit()
    return True


# --- Teacher enrollment ---

def create_pending_teacher(db: DbSession, owner_id: str, name: str) -> TeacherEnrollment:
    """Created synchronously in the API request; the worker fills in the embedding — see enroll_teacher_task."""
    teacher = TeacherEnrollment(owner_id=owner_id, name=name, status="pending")
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return teacher


def complete_teacher_enrollment(db: DbSession, teacher_id: str, embedding: list[float]) -> TeacherEnrollment | None:
    teacher = db.get(TeacherEnrollment, teacher_id)
    if teacher is None:
        return None
    teacher.embedding = embedding
    teacher.status = "ready"
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return teacher


def fail_teacher_enrollment(db: DbSession, teacher_id: str, error_detail: str) -> None:
    teacher = db.get(TeacherEnrollment, teacher_id)
    if teacher is None:
        return
    teacher.status = "failed"
    teacher.error_detail = error_detail
    db.add(teacher)
    db.commit()


def get_teacher(db: DbSession, owner_id: str, teacher_id: str) -> TeacherEnrollment | None:
    return (
        db.query(TeacherEnrollment)
        .filter(TeacherEnrollment.id == teacher_id, TeacherEnrollment.owner_id == owner_id)
        .first()
    )


def list_teachers(db: DbSession, owner_id: str) -> list[TeacherEnrollment]:
    return (
        db.query(TeacherEnrollment)
        .filter(TeacherEnrollment.owner_id == owner_id)
        .order_by(TeacherEnrollment.created_at.desc())
        .all()
    )


def delete_teacher(db: DbSession, owner_id: str, teacher_id: str) -> bool:
    teacher = get_teacher(db, owner_id, teacher_id)
    if teacher is None:
        return False
    db.delete(teacher)
    db.commit()
    return True


def get_enrolled_embeddings(db: DbSession, owner_id: str) -> list[tuple[str, list[float]]]:
    """Only status="ready" enrollments have a usable embedding — pending/failed ones are skipped."""
    return [
        (teacher.name, teacher.embedding)
        for teacher in list_teachers(db, owner_id)
        if teacher.status == "ready" and teacher.embedding is not None
    ]
