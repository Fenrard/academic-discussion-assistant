# Backend — Complete Module Reference

> Written 2026-09-15 as part of a full reverse-engineering documentation pass, by reading every
> file listed below directly. See `docs/ARCHITECTURE.md` for how these modules fit together and
> `docs/ML_PIPELINE.md` for the ML models specifically. Backend test suite confirmed passing this
> pass: `pytest tests/ -v` → **90 passed, 1 skipped**, run on this machine.

## How the backend starts

**API tier** (from the repo root, venv active):
```
uvicorn backend.main:app --reload
```
Entry point: `backend/main.py`. `--reload` is a dev convenience (auto-restarts on file changes);
drop it for anything resembling production. `backend/main.py`'s `lifespan()` context manager runs
`init_db()` (creates tables if they don't exist — a no-op against an already-Alembic-migrated
Postgres DB); **if no `CELERY_BROKER_URL` is configured (eager mode), it also preloads every ML
model at startup** (`backend.worker.celery_app.get_worker_models()`) before the app accepts any
traffic — added specifically to fix a reproduced bug where the very first WebSocket request against
a cold eager-mode backend could fail with a keepalive timeout, since eager mode would otherwise pay
the full model-load cost synchronously on whichever request happened to arrive first (see
`docs/TROUBLESHOOTING.md`). This branch never runs, and the API process still never imports an ML
library, when a real broker is configured — that's still a genuinely separate worker process's job
(`worker_process_init`'s `_preload_models()`). And, if `ENVIRONMENT=production` with no
`JWT_SECRET_KEY` set, exits immediately
rather than starting insecurely.

**Worker tier** (separate terminal, same venv):
```
celery -A backend.worker.celery_app worker --loglevel=info
```
On Windows specifically, add `--pool=solo` (Celery's default prefork pool needs `fork()`, which
Windows doesn't have). Entry point: `backend/worker/celery_app.py`. The `worker_process_init`
signal (`_preload_models()`) loads every ML model exactly once, before the worker starts accepting
tasks.

**Without a worker process running at all:** if `CELERY_BROKER_URL` is unset, every task runs
inline inside whichever process called `.delay()` — so the API process alone is a fully functional
(if not horizontally-scaled) system with zero extra processes. This is the default for local dev.

## Directory-by-directory, file-by-file

### `backend/main.py`
FastAPI app construction. Registers CORS (`allow_credentials=False` deliberately — auth is a
bearer token, never a cookie, so credentialed CORS mode buys nothing), the rate-limit exception
handler, `RequestContextMiddleware` (request-ID + timing logs), `MaxUploadSizeMiddleware`,
Prometheus instrumentation at `/metrics`, and every router under the `/api/v1` prefix. Also defines
`GET /health` (liveness only, no DB/worker check). **Calls:** `backend.api.{auth,minutes,sessions,
teacher,transcribe}`, `backend.core.config`, `backend.core.logging`, `backend.core.rate_limit`,
`backend.core.request_context`, `backend.database.db`. **Called by:** `uvicorn` directly (it's the
ASGI app object).

### `backend/core/config.py`
One plain `Settings` class (no pydantic-settings/dotenv dependency — deliberately minimal, matching
the style of the original dev scripts), instantiated once as `settings` and imported everywhere
else. Every environment variable the backend reads is declared here with its default — see
`docs/SETUP.md` §Environment Variables for the full annotated list. **Side effect at import time:**
creates `transcripts_dir` and the SQLite database file's parent directory if they don't exist.

### `backend/core/security.py`
Password hashing (`bcrypt` directly, not passlib — see `docs/TROUBLESHOOTING.md` for why) and JWT
issuing/verification (`PyJWT`, `HS256`, 12-hour expiry — "mobile app, not a browser session," per
its own comment). `get_current_user()` is the FastAPI dependency every authenticated route uses;
`get_current_user_from_token_string()` is the WebSocket-path equivalent (no `Depends()` chain is
available inside a WS handler, so the token has to be pulled from the query string and checked
manually — see `backend/api/transcribe.py`). **Calls:** `backend.database.db`, `backend.models.
user`. **Called by:** `backend.api.deps`, `backend.api.auth`, `backend.api.transcribe`.

### `backend/core/logging.py`
Structured JSON logging via stdlib `logging` only. Deliberately has **no** starlette/FastAPI
import — both tiers use this module, and the worker's `requirements-worker.txt` never installs
FastAPI's dependency tree, so an accidental starlette import here would silently break the worker
image the moment it was actually containerized. `request_id_ctx` (a `ContextVar`) is shared with
`request_context.py` across the module boundary intentionally.

### `backend/core/request_context.py`
The request-ID-aware HTTP middleware — genuinely needs starlette, so it's split out from
`logging.py` specifically to keep that module import-safe for the worker tier. Assigns/reuses a
request ID, logs `METHOD path -> status (Nms)` for every request, echoes the ID back as
`X-Request-ID`.

### `backend/core/rate_limit.py`
`slowapi`-based rate limiting (`limiter = Limiter(key_func=get_remote_address)`, applied per-route
via `@limiter.limit(...)` decorators on `/auth/login`, `/transcribe`, `/teachers/enroll`) plus
`MaxUploadSizeMiddleware`, which rejects an oversized `Content-Length` before FastAPI reads the
request body into memory at all (a malformed, non-integer `Content-Length` returns a clean `400`
rather than crashing).

### `backend/core/pubsub.py`
The worker↔API fan-out channel. See `docs/ARCHITECTURE.md` for the full explanation. Two
implementations behind one `subscribe()`/`publish_sync()` interface, selected by whether
`CELERY_BROKER_URL` is set.

### `backend/database/db.py`
SQLAlchemy engine + session setup. `DATABASE_URL` unset → SQLite file at `backend/database/
scaitale.db`. `pool_pre_ping=True` means a stale/dropped Postgres connection is transparently
discarded and reopened rather than failing one request. `get_db()` is the FastAPI dependency every
route uses to obtain a session (opens, yields, always closes in a `finally`).

### `backend/database/migrations/`
Alembic. `versions/0001_initial_schema.py` is the one migration that exists — creates `users`,
`sessions`, `teacher_enrollments`. Only relevant when `DATABASE_URL` points at Postgres; SQLite's
tables are created directly by `init_db()`'s `Base.metadata.create_all()` instead (no migration
history tracked for SQLite).

### `backend/models/` — SQLAlchemy ORM
- **`user.py`** — `User`: `id` (uuid hex), `email` (unique), `hashed_password`, `created_at`. One
  row per app-login account.
- **`session.py`** — `SessionRecord`: the big one. `id`, `owner_id` (FK → users), `title`, `status`
  (`in_progress|completed|failed|interrupted`), `created_at`, `updated_at`, `duration_seconds`,
  `consent_confirmed` (required True at creation), `pipeline_options` (JSON), `chunk_results` (JSON,
  the source of truth — see below), `transcript_text`, `transcript_segments` (JSON list),
  `speaker_segments` (JSON list), `keywords` (JSON list), `minutes` (JSON dict or null),
  `stage_latencies` (JSON dict). Deliberately denormalized — one row per session holds everything,
  no separate `segments` table. `to_summary_dict()` (list view) vs. `to_detail_dict()` (full view).
- **`teacher.py`** — `TeacherEnrollment`: `id`, `owner_id`, `name`, `status`
  (`pending|ready|failed`), `error_detail`, `embedding` (JSON list of floats, null until the worker
  finishes).

### `backend/schemas/` — Pydantic request/response shapes
- **`pipeline.py`** — `PipelineOptions`, the shared toggle schema described in `docs/ARCHITECTURE.md`
  §Contracts.
- **`session.py`** — `SessionSummary`/`SessionDetail` (API response shapes), `StartSessionMessage`/
  `EndSessionMessage` (WS control-frame shapes).
- **`auth.py`** — `UserCreate` (email + 8–72 char password — 72 is bcrypt's own hard byte limit),
  `UserOut`, `Token`.
- **`teacher.py`** — `TeacherOut`.

### `backend/services/` — the actual application logic

- **`audio_service.py`** — the pipeline orchestrator. See `docs/ML_PIPELINE.md` for full detail on
  every stage. Key functions: `ingest_audio()`, `clean_audio()`, `detect_speech()`,
  `transcribe_audio()`, `merge_transcript_with_speakers()`, `apply_teacher_verification()`,
  `run_pipeline()` (calls all of the above in the locked order), `load_whisper_model()`,
  `load_waveform()`. **Inputs:** a file path + a `LoadedModels` bundle + toggle flags. **Outputs:**
  a result dict (`text`, `language`, `whisper_segments`, `speaker_segments`, per-stage
  `stage_latencies`). **Side effects:** writes/cleans up temp FFmpeg intermediate files.
- **`diarization_service.py`** — pyannote wrapper: `load_diarization_model()`,
  `diarize_audio()` (note: `output.speaker_diarization.itertracks(yield_label=True)` — see
  `docs/TROUBLESHOOTING.md`, an earlier naive-unpacking version of this crashed on every real run),
  `format_speaker_segments()` (maps raw pyannote labels to `"Speaker A"/"Speaker B"...` by
  first-appearance order).
- **`teacher_verification_service.py`** — `load_verification_model()`, `extract_embedding()`,
  `cosine_similarity()`, `verify_segment()`. See `docs/ML_PIPELINE.md`.
- **`glossary_service.py`** — `Glossary` class (case-insensitive match, case-preserving
  replacement, longest-phrase-first), `load_glossary()` (reads `backend/data/glossary.json`, a
  hand-maintained starter list — see its own `_meta` field).
- **`keyword_service.py`** — `build_weighted_text()` (repeats teacher-labeled segment text before
  extraction, so instructional speech dominates the keyword graph), `extract_keywords()`
  (from-scratch TextRank on `networkx`: tokenize → drop trilingual stopwords → co-occurrence graph
  → PageRank, `max_iter=200` with a weighted-degree-centrality fallback on non-convergence → merge
  adjacent top tokens into keyphrases).
- **`minutes_service.py`** — `generate_minutes()`: silence-gap topic grouping
  (`topic_gap_seconds`, default 8.0s), teacher-prioritized key-point ranking, regex-pattern
  definition extraction (trilingual), regex trigger-phrase action-item flagging (trilingual),
  `teacher_speech_ratio`/`teacher_speakers` computation. Explicitly a heuristic, not an NLP model —
  its own module docstring says so.
- **`session_service.py`** — the glue between the DB and everything above. Key functions:
  `create_session()` (refuses if `consent_confirmed` isn't True), `append_chunk_result()` (writes
  into `chunk_results`, recomputes the visible transcript from the longest *contiguous* prefix by
  chunk index — this is what makes out-of-order chunk completion safe), `finalize_session()` (runs
  keyword extraction + minutes generation, marks the session `"completed"`), `get_session()`,
  `list_sessions()`, `delete_session()`, plus the teacher-enrollment equivalents
  (`create_pending_teacher()`, `complete_teacher_enrollment()`, `fail_teacher_enrollment()`,
  `get_enrolled_embeddings()`).
- **`user_service.py`** — `register_user()`, `authenticate_user()`, `get_user_by_email()`. Thin
  wrapper around `security.py`'s hashing functions plus DB reads/writes.

### `backend/api/` — HTTP + WebSocket route handlers
- **`auth.py`** — `POST /auth/register`, `POST /auth/login` (rate-limited).
- **`transcribe.py`** — `POST /transcribe` (whole-file, async 202+poll), `WS /ws/transcribe` (the
  streaming path — see `docs/ARCHITECTURE.md` for the full trace).
- **`sessions.py`** — `GET /sessions`, `GET /sessions/{id}`, `DELETE /sessions/{id}`.
- **`teacher.py`** — `POST /teachers/enroll` (async), `GET /teachers`, `GET /teachers/{id}`,
  `DELETE /teachers/{id}`.
- **`minutes.py`** — `GET /sessions/{id}/minutes`, `GET /sessions/{id}/minutes/export`.
- **`deps.py`** — just re-exports `get_current_user` and `get_db` from one place so every router
  needs only one import line.

Full request/response shapes for every route: `docs/API.md`.

### `backend/worker/`
- **`celery_app.py`** — the Celery app object, task-discovery config, and `_load_models()`/
  `get_worker_models()` (the once-per-worker-process model loading). Imports every ORM model
  module explicitly at the top (`import backend.models.session` etc.) — necessary because a
  standalone worker process starts with a blank SQLAlchemy metadata state, unlike the API process
  which gets all three transitively. Without this, a worker-tier `SessionRecord` insert fails with
  `NoReferencedTableError` looking up the `users` foreign key — a real bug this project's history
  records catching only by running a genuinely separate worker process against real Postgres, not
  by eager mode (which shares the API process's already-populated metadata and never surfaces it).
- **`tasks.py`** — the actual task functions: `transcribe_chunk_task`, `transcribe_file_task`,
  `enroll_teacher_task`. Each writes the incoming base64 audio to a temp file, runs the pipeline,
  persists the result, publishes to pub/sub, cleans up the temp file in a `finally`. Deliberately
  keeps `audio_service`'s import **lazy** (inside each function body) so that importing this module
  from the API process (to get `.delay()`-able task objects) stays cheap.

### `backend/utils/audio_io.py`
`write_temp_audio()`/`cleanup_temp_files()` — shared temp-file helpers for both the upload path and
the streaming path. Temp files land in `<system temp dir>/scaitale/`.

## Request/response formats — quick reference

See `docs/API.md` for the complete, per-route reference. In brief: every REST route (except
`/health`, `/auth/register`, `/auth/login`) requires `Authorization: Bearer <JWT>`. The WebSocket
route authenticates via a `?token=<JWT>` query parameter instead (browsers/Flutter's WS client
can't set a custom header on the opening handshake). All request/response bodies are JSON except
file uploads (`multipart/form-data`) and the minutes export (`text/plain`).

## Audio formats

Accepted input extensions (`backend/services/audio_service.py: SUPPORTED_EXTENSIONS`, kept in sync
with an identical constant in `scripts/preprocess_audio.py`): `.wav .mp3 .m4a .ogg .webm .flac .aac
.3gp .3gpp .amr .mp4 .mov .opus .wma`. FFmpeg sniffs the actual container/codec bytes, not the file
extension — the extension allowlist only gates which files are even attempted. Every input is
standardized to **16kHz, mono, 16-bit PCM WAV** before anything else touches it
(`ingest_audio()`) — this is the one pipeline stage with no toggle.

## Model initialization, loading, caching, GPU/CPU

Covered in full in `docs/ML_PIPELINE.md`. In brief: every model is loaded exactly once per worker
process (`worker_process_init` signal), never per-request. **CPU only** in the currently-installed
environment — see `CLAUDE.md` Part 1C's GPU note.

## Threading / async / queues

The API tier is a single-threaded `asyncio` event loop (standard for FastAPI/uvicorn without
extra worker processes) — this is exactly why it must never run CPU-bound code inline. The worker
tier's concurrency model is Celery's own (`--concurrency=N` spins up N worker sub-processes on the
prefork pool; `--pool=solo` on Windows runs single-threaded per worker process, since Windows has
no `fork()`).

## Temporary vs. permanent files

**Temporary** (always cleaned up in a `finally` block, never left behind on success *or* failure):
every raw audio upload/chunk (`<temp dir>/scaitale/*.wav`), every FFmpeg intermediate (`*_std.wav`,
`*_cleaned.wav`, written alongside the input and unlinked after each pipeline stage). **Permanent:**
the database file/rows (transcripts, minutes, keywords — but never raw audio), and whatever a
developer manually saves into `recordings/`/`models/`/`datasets/` (all gitignored, all outside the
pipeline's own temp-file lifecycle).

## Error handling, logging, cleanup

Every Celery task wraps its body in `try/except Exception` — a failure publishes an `{"type":
"error", ...}` message to pub/sub (so a connected client sees it) **and** logs it via the structured
logger (so a failure is visible even if no client is connected to see the pub/sub message).
`cleanup_temp_files()` runs in a `finally`, is exception-safe itself (a missing/locked file is
silently ignored, never raised). HTTP routes raise `HTTPException` with an appropriate status code
for expected failure modes (404 for a missing session, 409 for "minutes not generated yet", 400 for
a malformed request) — genuinely unexpected exceptions propagate up to `RequestContextMiddleware`,
which logs them with a full traceback before FastAPI's own default 500 handler takes over.

## Database — full reference

**Engine:** SQLite (default, zero-config, file at `backend/database/scaitale.db`) or PostgreSQL
(any version compatible with `psycopg[binary]==3.3.4` — the docker-compose/CI setup uses
`postgres:16-alpine`), selected entirely by whether `DATABASE_URL` is set.

**Schema** (three tables, all defined in `backend/models/`, migration in `backend/database/
migrations/versions/0001_initial_schema.py`):

| Table | Key columns | Relationships |
|---|---|---|
| `users` | `id` (PK), `email` (unique), `hashed_password`, `created_at` | Referenced by `sessions.owner_id` and `teacher_enrollments.owner_id` |
| `sessions` | `id` (PK), `owner_id` (FK), `status`, `chunk_results` (JSON), `transcript_text`, `transcript_segments` (JSON), `keywords` (JSON), `minutes` (JSON), `stage_latencies` (JSON) | Belongs to one `users` row |
| `teacher_enrollments` | `id` (PK), `owner_id` (FK), `name`, `status`, `embedding` (JSON list[float]) | Belongs to one `users` row |

No foreign key from `sessions`/`teacher_enrollments` to each other — teacher verification at
inference time reads *all* of an owner's `ready` teacher enrollments (`session_service.
get_enrolled_embeddings()`) and compares against each; there's no per-session "which teacher"
selection stored anywhere beyond what each transcript segment's `is_teacher`/`teacher_name` fields
record after the fact.

**Migrations:** `alembic upgrade head` (from the repo root, `DATABASE_URL` pointed at Postgres) —
only one migration exists (`0001_initial_schema`). SQLite never runs migrations; `init_db()`'s
`Base.metadata.create_all(bind=engine, checkfirst=True)` creates whatever tables don't already
exist, every time the app starts.

**Initialization:** automatic — `init_db()` is called from both `backend/main.py`'s `lifespan()`
and `backend/worker/celery_app.py`'s `_load_models()`, so either process starting fresh against an
empty SQLite file will create the schema itself. Postgres deployments should run `alembic upgrade
head` explicitly as the source of truth (the docker-compose `migrate` service does this as a
one-shot container before `api`/`worker` start).

**CRUD:** all through `backend/services/session_service.py` and `user_service.py` — no raw SQL
anywhere in the codebase; everything goes through SQLAlchemy's ORM query API.

**Seed data:** **NONE EXISTS.** No fixture/seed script anywhere in the repository. A fresh database
starts completely empty; the first user must register via `POST /auth/register`.

**Reset procedure:** SQLite — delete `backend/database/scaitale.db` and restart the API (it
recreates the schema automatically, empty). Postgres — `alembic downgrade base && alembic upgrade
head`, or drop and recreate the database, then `alembic upgrade head`.

**Backup procedure:** **NOT IMPLEMENTED / NOT DOCUMENTED ANYWHERE IN THIS REPOSITORY.** For SQLite,
copying `scaitale.db` while the API isn't running is the obvious approach but is not something this
project has any tooling for. For Postgres, standard `pg_dump`/`pg_restore` would apply but no
project-specific wrapper or scheduled backup exists — **UNKNOWN / not addressed**, since no
production deployment of this project has actually happened yet to need it.
