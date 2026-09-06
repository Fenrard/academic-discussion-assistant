"""
A real concurrency test against a real Postgres instance -- everything
else in tests/ runs against the SQLite default (see conftest.py), which
can't actually exercise row-level locking (SQLite's dialect has no
FOR UPDATE; it serializes writes at the whole-database level instead).
This one file is skipped unless DATABASE_URL is already pointing at a
real Postgres before pytest starts, matching how CI's own service
containers run the full suite: `DATABASE_URL=postgresql+psycopg://...
pytest tests/test_session_service.py`.
"""

import os
import threading
import time
import uuid

import pytest

from backend.database.db import SessionLocal, init_db
from backend.models.session import SessionRecord
from backend.schemas.pipeline import PipelineOptions
from backend.services import session_service, user_service

_USING_POSTGRES = os.environ.get("DATABASE_URL", "").startswith("postgresql")


def _chunk(text: str) -> dict:
    return {
        "text": text,
        "language": "en",
        "whisper_segments": [{"start": 0.0, "end": 1.0, "text": text}],
        "speaker_segments": [],
        "audio_duration_seconds": 1.0,
        "stage_latencies": {},
    }


@pytest.mark.skipif(
    not _USING_POSTGRES,
    reason="Row-level locking only actually locks on Postgres (SQLite has no FOR UPDATE) -- "
    "run with DATABASE_URL pointing at a real Postgres to exercise this.",
)
def test_append_chunk_result_survives_two_concurrent_writers(monkeypatch):
    """
    Two threads, each with its own DB session -- mirroring two separate
    Celery worker processes completing different chunks of the same
    session near-simultaneously. Without append_chunk_result's row lock
    (db.refresh(session, with_for_update=True)), whichever thread commits
    last silently overwrites the other's chunk (a lost update).
    """
    init_db()

    setup_db = SessionLocal()
    user = user_service.register_user(setup_db, f"race-test-{uuid.uuid4().hex}@example.com", "testpassword123")
    session = session_service.create_session(setup_db, user.id, "race test", PipelineOptions(), consent_confirmed=True)
    user_id, session_id = user.id, session.id
    setup_db.close()

    # Widens the window each thread holds the row lock, so the two calls
    # reliably contend for it regardless of Python thread-scheduling luck --
    # without this, the two commits might happen to run back-to-back with no
    # actual overlap, and the test wouldn't be exercising the lock at all.
    # Patched on the module (not the object) since append_chunk_result calls
    # materialize_transcript as a bare same-module name, resolved from
    # session_service's own globals at call time.
    real_materialize = session_service.materialize_transcript

    def _slow_materialize(chunk_results):
        time.sleep(0.3)
        return real_materialize(chunk_results)

    monkeypatch.setattr(session_service, "materialize_transcript", _slow_materialize)

    errors: list[Exception] = []

    def worker(chunk_index: int, text: str) -> None:
        db = SessionLocal()
        try:
            loaded = db.get(SessionRecord, session_id)
            session_service.append_chunk_result(db, loaded, chunk_index, _chunk(text))
        except Exception as error:  # surfaced via `errors`, not silently lost inside the thread
            errors.append(error)
        finally:
            db.close()

    threads = [threading.Thread(target=worker, args=(i, text)) for i, text in enumerate(["hello", "world"])]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert not errors, f"worker thread(s) raised: {errors}"

    verify_db = SessionLocal()
    final = session_service.get_session(verify_db, user_id, session_id)
    verify_db.close()

    assert set(final.chunk_results.keys()) == {"0", "1"}, (
        f"Lost update: expected both chunks present, got {sorted(final.chunk_results.keys())}"
    )
    assert final.transcript_text == "hello world"
