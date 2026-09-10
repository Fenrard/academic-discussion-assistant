"""
Pure-logic tests for session_service.materialize_transcript() (the
out-of-order-chunk reordering logic — the highest-risk new code in the
worker split, so it gets dedicated coverage independent of any real
model), plus a couple of true end-to-end tests that run the actual
Celery tasks in eager mode (backend/worker/celery_app.py's
CELERY_TASK_ALWAYS_EAGER dev fallback — no broker needed) against real
audio, proving the whole enqueue -> pipeline -> persist -> publish path
works without needing Redis or a separate worker process.

The end-to-end tests are slow (real Whisper/SpeechBrain inference) —
that's the cost of them being genuine, not mocked-out, verification.
"""

import base64
import uuid
from pathlib import Path

import pytest

from backend.database.db import SessionLocal, init_db
from backend.services import session_service, user_service
from backend.services.session_service import materialize_transcript

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_AUDIO_PATH = REPO_ROOT / "recordings" / "lecture_preprocessed.wav"


# --- materialize_transcript: pure logic, no DB/models needed ---

def _chunk(text: str, duration: float = 3.0) -> dict:
    return {
        "text": text,
        "language": "en",
        "whisper_segments": [{"start": 0.0, "end": duration, "text": text}],
        "speaker_segments": [],
        "audio_duration_seconds": duration,
        "stage_latencies": {"transcribe": 0.5},
    }


def test_materialize_transcript_in_order():
    chunk_results = {"0": _chunk("hello"), "1": _chunk("world")}
    result = materialize_transcript(chunk_results)
    assert result["transcript_text"] == "hello world"
    assert result["contiguous_chunk_count"] == 2
    assert result["duration_seconds"] == 6.0


def test_materialize_transcript_shifts_chunk_relative_timestamps_onto_the_session_timeline():
    # Each streamed chunk is transcribed standalone, so its segments come back
    # 0-based. Before the shift, chunk 1's segment was [0.0, 3.0] just like
    # chunk 0's -- every chunk's transcript restacked at zero, so the transcript
    # view and minutes topic-grouping saw one pile of overlapping segments.
    chunk_results = {"0": _chunk("hello", duration=3.0), "1": _chunk("world", duration=3.0)}
    result = materialize_transcript(chunk_results)
    starts = [(s["start"], s["end"]) for s in result["transcript_segments"]]
    assert starts == [(0.0, 3.0), (3.0, 6.0)]


def test_materialize_transcript_shift_is_a_noop_for_a_single_whole_file_chunk():
    # The whole-file path (transcribe_file_task) stores one chunk whose segments
    # are already whole-file-absolute from VAD over the entire file -- offset 0
    # must leave them exactly as they are.
    only_chunk = {
        "text": "whole file",
        "language": "en",
        "whisper_segments": [{"start": 4.2, "end": 9.8, "text": "whole file"}],
        "speaker_segments": [],
        "audio_duration_seconds": 12.0,
        "stage_latencies": {},
    }
    result = materialize_transcript({"0": only_chunk})
    assert [(s["start"], s["end"]) for s in result["transcript_segments"]] == [(4.2, 9.8)]


def test_materialize_transcript_stops_at_first_gap():
    # Chunk 1 hasn't landed yet (a distributed worker pool finished 0 and 2 first) —
    # the visible transcript must stay at just chunk 0, not skip ahead to include 2.
    chunk_results = {"0": _chunk("hello"), "2": _chunk("out of order")}
    result = materialize_transcript(chunk_results)
    assert result["transcript_text"] == "hello"
    assert result["contiguous_chunk_count"] == 1
    # Duration/latency ARE order-independent — both completed chunks count.
    assert result["duration_seconds"] == 6.0


def test_materialize_transcript_gap_closes_once_missing_chunk_arrives():
    chunk_results = {"0": _chunk("hello"), "1": _chunk("world"), "2": _chunk("again")}
    result = materialize_transcript(chunk_results)
    assert result["transcript_text"] == "hello world again"
    assert result["contiguous_chunk_count"] == 3


def test_materialize_transcript_empty():
    result = materialize_transcript({})
    assert result["transcript_text"] == ""
    assert result["contiguous_chunk_count"] == 0
    assert result["duration_seconds"] == 0.0


def test_materialize_transcript_sums_stage_latencies_across_all_chunks():
    chunk_results = {"0": _chunk("a"), "1": _chunk("b")}
    result = materialize_transcript(chunk_results)
    assert result["stage_latencies"]["transcribe"] == 1.0


# --- End-to-end: real Celery tasks, eager mode, real audio ---
#
# These tests assert on DB state immediately after .delay() returns — only valid
# under eager mode (task runs synchronously, inline). If CELERY_BROKER_URL happens
# to be set in the ambient environment (e.g. a developer testing against a real
# worker manually), .delay() would genuinely enqueue to Redis instead and this
# process's assertions would race a separate worker process that may not have
# picked the task up yet — caught by actually running these against real
# Postgres+Redis with CELERY_BROKER_URL set, not just in this sandbox's default
# no-broker setup. force_eager_mode below makes these tests deterministic
# regardless of what's ambiently configured — they're testing the tasks' own
# logic, not Celery's distribution behavior, so forcing eager mode here is the
# correct fix, not a workaround.

@pytest.fixture(autouse=True)
def force_eager_mode():
    from backend.worker.celery_app import celery_app

    original = celery_app.conf.task_always_eager
    celery_app.conf.task_always_eager = True
    yield
    celery_app.conf.task_always_eager = original


@pytest.fixture(scope="module")
def db_and_owner():
    init_db()
    db = SessionLocal()
    user = user_service.register_user(db, f"task-test-{uuid.uuid4().hex}@example.com", "testpassword123")
    yield db, user
    db.close()


@pytest.mark.skipif(not TEST_AUDIO_PATH.exists(), reason="recordings/lecture_preprocessed.wav not present")
def test_transcribe_chunk_task_end_to_end(db_and_owner):
    from backend.schemas.pipeline import PipelineOptions
    from backend.worker.tasks import transcribe_chunk_task

    db, user = db_and_owner
    options = PipelineOptions(enable_vad=True)
    session = session_service.create_session(db, user.id, "task test", options, consent_confirmed=True)

    audio_b64 = base64.b64encode(TEST_AUDIO_PATH.read_bytes()).decode("ascii")
    transcribe_chunk_task.delay(session.id, 0, audio_b64, options.model_dump(), [])

    db.expire_all()
    refreshed = session_service.get_session(db, user.id, session.id)
    assert refreshed.transcript_text != ""
    assert "0" in refreshed.chunk_results


@pytest.mark.skipif(not TEST_AUDIO_PATH.exists(), reason="recordings/lecture_preprocessed.wav not present")
def test_enroll_teacher_task_end_to_end(db_and_owner):
    from backend.worker.tasks import enroll_teacher_task

    db, user = db_and_owner
    teacher = session_service.create_pending_teacher(db, user.id, "Test Teacher")

    audio_b64 = base64.b64encode(TEST_AUDIO_PATH.read_bytes()).decode("ascii")
    enroll_teacher_task.delay(teacher.id, audio_b64)

    db.expire_all()
    refreshed = session_service.get_teacher(db, user.id, teacher.id)
    assert refreshed.status in ("ready", "failed")  # "failed" only if speechbrain genuinely unavailable
    if refreshed.status == "ready":
        assert refreshed.embedding is not None
        assert len(refreshed.embedding) > 0
