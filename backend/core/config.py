"""
Central, plain-module configuration. No pydantic-settings / dotenv
dependency — same minimalist style as the existing scripts/, just
os.environ with sane defaults. Import `settings` everywhere else.
"""

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


class Settings:
    # --- Paths ---
    repo_root: Path = REPO_ROOT
    recordings_dir: Path = REPO_ROOT / "recordings"
    transcripts_dir: Path = REPO_ROOT / "transcripts"
    glossary_path: Path = BACKEND_DIR / "data" / "glossary.json"
    database_path: Path = BACKEND_DIR / "database" / "scaitale.db"

    # --- Database ---
    database_url: str = os.environ.get(
        "DATABASE_URL", f"sqlite:///{database_path.as_posix()}"
    )

    # --- Hugging Face (pyannote diarization) ---
    hf_token: str | None = os.environ.get("HF_TOKEN")

    # --- Whisper ---
    whisper_model_size: str = os.environ.get("WHISPER_MODEL_SIZE", "small")
    whisper_device: str = os.environ.get("WHISPER_DEVICE", "cpu")
    whisper_compute_type: str = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
    # 0 = CTranslate2's own default. Set to the host's physical core count for
    # a single-worker (--concurrency=1) deployment; leave 0 when running a
    # multi-process worker pool so the cores aren't oversubscribed.
    whisper_cpu_threads: int = int(os.environ.get("WHISPER_CPU_THREADS", "0"))

    # --- Audio ---
    sample_rate: int = 16000
    min_chunk_duration_seconds: float = 1.0
    max_chunk_duration_seconds: float = 10.0

    # --- Teacher verification (SpeechBrain ECAPA-TDNN) ---
    speaker_verification_model: str = "speechbrain/spkrec-ecapa-voxceleb"
    # Cosine similarity on ECAPA embeddings; typical VoxCeleb EER operating
    # point. Not yet calibrated against real classroom data — tune once
    # evaluation/ has teacher-ID precision/recall numbers.
    teacher_verification_threshold: float = float(
        os.environ.get("TEACHER_VERIFICATION_THRESHOLD", "0.35")
    )

    # --- Minutes / keywords ---
    keyword_count: int = 10
    topic_gap_seconds: float = 8.0  # silence gap that starts a new minutes "topic" block

    # --- CORS (Flutter dev client) ---
    cors_allow_origins: list[str] = ["*"]

    # --- Environment ---
    # "development" (default) enables permissive local behavior (docs exposed, no
    # required HTTPS assumptions); "production" is checked by main.py to fail loudly
    # on missing secrets rather than silently running insecurely.
    environment: str = os.environ.get("ENVIRONMENT", "development")

    # --- Celery / Redis (async inference — see backend/worker/) ---
    # Unset -> CELERY_TASK_ALWAYS_EAGER, tasks run inline with no broker needed
    # (this sandbox's local/test default). Set both for real horizontal scaling.
    # 127.0.0.1, not "localhost": on a dual-stack host (Windows 11, and any
    # Linux box with IPv6 enabled) "localhost" resolves to ::1 first, and if
    # Redis/Memurai only listens on IPv4 the async client eats a multi-second
    # stall — or an outright connect timeout — on every connection while the
    # ::1 attempt is refused. A real deployment overrides these with the
    # service hostname anyway (deployment/docker-compose.yml -> redis://redis).
    celery_broker_url: str | None = os.environ.get("CELERY_BROKER_URL")
    celery_result_backend: str | None = os.environ.get("CELERY_RESULT_BACKEND", celery_broker_url)
    redis_url: str = os.environ.get("REDIS_URL", celery_broker_url or "redis://127.0.0.1:6379/0")

    # --- Rate limiting / upload limits ---
    max_upload_bytes: int = int(os.environ.get("MAX_UPLOAD_BYTES", str(200 * 1024 * 1024)))  # 200MB
    rate_limit_login: str = os.environ.get("RATE_LIMIT_LOGIN", "10/minute")
    rate_limit_transcribe: str = os.environ.get("RATE_LIMIT_TRANSCRIBE", "30/minute")
    rate_limit_enroll: str = os.environ.get("RATE_LIMIT_ENROLL", "10/minute")

    # --- Observability ---
    sentry_dsn: str | None = os.environ.get("SENTRY_DSN")
    log_level: str = os.environ.get("LOG_LEVEL", "INFO")


settings = Settings()
settings.database_path.parent.mkdir(parents=True, exist_ok=True)
settings.transcripts_dir.mkdir(parents=True, exist_ok=True)
