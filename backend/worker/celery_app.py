"""
Celery app — the inference tier. This is what actually fixes the
blocking-event-loop bug: backend/api/transcribe.py no longer runs
Whisper/pyannote/SpeechBrain itself, it enqueues a task here and a
separate worker process (`celery -A backend.worker.celery_app worker`)
does the CPU-bound work, so the API's event loop is never blocked and
inference scales independently of API traffic (`celery worker --concurrency=N`,
or more worker containers — see deployment/docker-compose.yml).

No broker configured -> CELERY_TASK_ALWAYS_EAGER: tasks run inline, in
the calling process, synchronously — this is Celery's own documented
testing pattern, not a hack, and it's what keeps this app runnable in
a dev/CI sandbox with no Redis installed.
"""

from celery import Celery
from celery.signals import worker_process_init

from backend.core.config import settings
from backend.core.logging import configure_logging, get_logger

configure_logging(settings.log_level)
_logger = get_logger("scaitale.worker")

# Registers every ORM model on Base.metadata in THIS process. Each Python process has
# its own SQLAlchemy metadata state — the API process gets all three imported
# transitively (backend.core.security imports User, backend.worker.tasks imports
# SessionRecord, etc.), but a real worker process run standalone
# (`celery -A backend.worker.celery_app worker`) starts from a blank slate. Without
# this, SQLAlchemy can create/flush a `sessions` row's foreign key to `users` in the
# API process fine, then the exact same operation fails in the worker process with
# `NoReferencedTableError: ... could not find table 'users'` — caught by actually
# running a real separate worker process against real Postgres+Redis, not just eager
# mode (which never surfaces this, since eager mode shares the API process's already-
# fully-populated metadata).
import backend.models.session  # noqa: E402,F401
import backend.models.teacher  # noqa: E402,F401
import backend.models.user  # noqa: E402,F401

celery_app = Celery(
    "scaitale",
    broker=settings.celery_broker_url or "memory://",
    backend=settings.celery_result_backend or "cache+memory://",
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_always_eager=settings.celery_broker_url is None,
    task_eager_propagates=True,  # so eager-mode test/dev failures raise instead of hiding in a result object
)

celery_app.autodiscover_tasks(["backend.worker"])


# --- Once-per-worker-process model loading ---
# Mirrors the "loaded once, passed in, never per call" rule from the original
# single-process design — just relocated to the worker tier. Each Celery worker
# process (prefork pool = one process per --concurrency slot) gets its own
# LoadedModels, loaded exactly once via this signal, then reused by every task
# that process picks up. Module-level, not app.state, because a worker process
# has no FastAPI app.
_worker_models = None


def get_worker_models():
    """Lazy-loads on first use if the init signal didn't already run (e.g. eager/test mode)."""
    global _worker_models
    if _worker_models is None:
        _worker_models = _load_models()
    return _worker_models


def _load_models():
    """
    Same graceful-degradation logic backend/main.py's lifespan used to
    run — relocated here wholesale, since the worker tier is now the
    only process that loads any of these. Whisper is the one hard
    requirement (transcription is the app's core function); VAD,
    diarization, and teacher verification are each independently
    optional per CLAUDE.md's toggles, so a missing/failed one only
    disables its own toggle rather than the whole worker.
    """
    from silero_vad import load_silero_vad

    from backend.core.config import settings
    from backend.database.db import init_db
    from backend.services.audio_service import LoadedModels, load_whisper_model
    from backend.services.diarization_service import load_diarization_model
    from backend.services.glossary_service import load_glossary
    from backend.services.teacher_verification_service import load_verification_model

    # Defensive, not redundant: backend/main.py's lifespan calls this too,
    # but a standalone worker process (`celery -A backend.worker.celery_app
    # worker`) started before the API against a fresh SQLite dev DB would
    # otherwise hit "no such table" the moment a task touches SessionRecord.
    # A no-op against a Postgres DB Alembic already migrated (checkfirst=True
    # is create_all()'s default) — see init_db()'s own docstring.
    init_db()

    whisper_model = load_whisper_model()
    glossary = load_glossary()

    silero_vad_model = None
    try:
        silero_vad_model = load_silero_vad()
    except Exception as error:
        _logger.warning(f"Silero VAD failed to load, enable_vad requests will fail: {error}")

    diarization_model = None
    if settings.hf_token:
        try:
            diarization_model = load_diarization_model(settings.hf_token)
        except Exception as error:
            _logger.warning(f"Diarization model failed to load, enable_diarization requests will fail: {error}")
    else:
        _logger.info("HF_TOKEN not set — diarization unavailable until it is.")

    teacher_verification_model = None
    try:
        teacher_verification_model = load_verification_model()
    except Exception as error:
        _logger.warning(f"Teacher verification model unavailable, enable_teacher_verification requests will fail: {error}")

    return LoadedModels(
        whisper_model=whisper_model,
        diarization_model=diarization_model,
        teacher_verification_model=teacher_verification_model,
        silero_vad_model=silero_vad_model,
        glossary=glossary,
    )


@worker_process_init.connect
def _preload_models(**_kwargs):
    """Runs once when a real Celery worker process boots (prefork pool) — not in eager mode."""
    global _worker_models
    _worker_models = _load_models()
