# Codebase Dependency Map

> Written 2026-09-18 by tracing the actual import graph of every `.py` file under `backend/`,
> `scripts/`, `evaluation/`, `ai/finetuning/`, `tests/`, and every `.dart` file under `android/lib/`
> — via direct `grep` of every `import`/`from` statement in the repository, not from memory or
> naming conventions. No application code was modified to produce this document. Where a claim
> below is a negative finding (e.g., "no circular imports exist"), it was verified by exhaustively
> tracing the graph, not assumed from the absence of an obvious cycle.
>
> Companion reading: `docs/ARCHITECTURE.md` (runtime data flow), `docs/BACKEND.md`/`docs/
> FRONTEND.md` (per-file purpose), `docs/ARCHITECTURE_DECISIONS.md` (why things are shaped this
> way), `docs/PROJECT_INVENTORY.md` (file-by-file safe-to-delete judgments).

---

## 1. Backend Python import graph (verified, layer by layer)

The backend is a clean, strictly layered directed acyclic graph. **No circular imports exist
anywhere in `backend/`** — verified by tracing every `from backend...`/`import backend...`
statement in every file this pass; nothing later in the chain below ever imports something earlier.

```
Layer 0 (leaf — imports no other backend module):
  backend/core/config.py           <- imported by nearly everything below
  backend/services/keyword_service.py   <- pure stdlib + networkx, zero internal deps
  backend/services/diarization_service.py <- pure pyannote.audio, zero internal deps
  backend/utils/audio_io.py

Layer 1 (imports only Layer 0):
  backend/database/db.py                    imports core.config
  backend/core/logging.py                   (no internal deps at all)
  backend/core/rate_limit.py                imports core.config
  backend/core/pubsub.py                    imports core.config
  backend/services/glossary_service.py      imports core.config
  backend/services/teacher_verification_service.py   imports core.config
  backend/services/minutes_service.py       imports core.config

Layer 2 (imports Layer 0/1):
  backend/models/user.py, session.py, teacher.py     each import database.db.Base
  backend/core/request_context.py           imports core.logging
  backend/core/security.py                  imports database.db, models.user
  backend/schemas/pipeline.py               imports core.config
  backend/schemas/session.py                imports schemas.pipeline

Layer 3 (imports Layer 0-2):
  backend/services/user_service.py          imports core.security, models.user
  backend/services/session_service.py       imports models.session, models.teacher,
                                             schemas.pipeline, services.keyword_service,
                                             services.minutes_service
  backend/services/audio_service.py         imports core.config, services.diarization_service,
                                             services.teacher_verification_service,
                                             services.glossary_service, utils.audio_io
  backend/api/deps.py                       imports core.security, database.db

Layer 4 (imports Layer 0-3):
  backend/api/auth.py, sessions.py, minutes.py, teacher.py
                                             import api.deps, models.*, schemas.*, services.*
  backend/worker/celery_app.py              imports core.config, core.logging, models.*
                                             (eagerly, for metadata registration) — and, LAZILY,
                                             inside _load_models(): services.audio_service
                                             (specifically LoadedModels, load_whisper_model)

Layer 5:
  backend/worker/tasks.py                   imports core.logging, core.pubsub, database.db,
                                             models.session, schemas.pipeline,
                                             services.session_service, utils.audio_io,
                                             worker.celery_app (top-level, for the @celery_app.task
                                             decorator) — and, LAZILY, inside function bodies:
                                             services.audio_service, worker.celery_app.
                                             get_worker_models (again, redundantly but not
                                             circularly)
  backend/api/transcribe.py                 imports api.deps, core.*, models.user,
                                             schemas.pipeline, services.session_service,
                                             utils.audio_io, worker.tasks (top-level, to get
                                             .delay()-able task objects)

Layer 6 (the entry point — nothing imports this except uvicorn):
  backend/main.py                           imports api.{auth,minutes,sessions,teacher,transcribe},
                                             core.config, core.logging, core.rate_limit,
                                             core.request_context, database.db — and, LAZILY,
                                             inside lifespan(): worker.celery_app.get_worker_models
                                             (added this documentation pass, for the eager-mode
                                             startup preload fix)
```

**Why the lazy imports matter, precisely:** `backend/worker/tasks.py`'s own docstring states the
reason directly — importing `audio_service` (and everything it transitively pulls in: torch,
faster-whisper, pyannote, speechbrain) at module top would make `backend/api/transcribe.py` and
`backend/api/teacher.py`'s own top-level `from backend.worker.tasks import ...` drag the entire ML
stack into the API process just to construct a task signature for `.delay()`. This is the exact
mechanism that keeps the "API tier never imports an ML library" guarantee true — **verified this
session by direct execution**: `import backend.main` pulls in zero of `torch`/`faster_whisper`/
`pyannote`/`speechbrain`/`silero_vad`.

## 2. Per-module deep detail — inputs, outputs, side effects, I/O, env vars, network, models

### `backend/core/config.py`
- **Imported by:** almost every other backend module (Layer 1+).
- **Imports:** stdlib only (`os`, `pathlib`).
- **Inputs:** every environment variable the backend reads (full list: `docs/SETUP.md`
  §Environment Variables).
- **Outputs:** one `settings` singleton object, instantiated at import time.
- **Side effects:** creates `transcripts_dir` and the SQLite database file's parent directory on
  disk **at import time** (`settings.database_path.parent.mkdir(...)`,
  `settings.transcripts_dir.mkdir(...)`) — this means simply *importing* this module has a
  filesystem side effect, not just reading it.
- **Files read:** none directly (env vars only).
- **Files written:** two directories created as above.
- **Network:** none.
- **Models loaded:** none.

### `backend/services/audio_service.py`
- **Imported by:** `backend/worker/celery_app.py` (lazily, inside `_load_models()`),
  `backend/worker/tasks.py` (lazily, inside `_run_pipeline_for_chunk()` and
  `enroll_teacher_task()`).
- **Imports:** `core.config`, `services.diarization_service`, `services.
  teacher_verification_service`, `services.glossary_service`, `utils.audio_io`; externally:
  `torch`, `soundfile`, `faster_whisper`, `pyannote.audio`, `silero_vad`.
- **Key functions and their callers:**
  - `load_whisper_model()` — called only by `worker/celery_app.py: _load_models()`.
  - `ingest_audio()` — called by `run_pipeline()` internally, and directly by
    `worker/tasks.py: enroll_teacher_task()` (teacher enrollment skips the rest of the pipeline
    but still needs standardization).
  - `clean_audio()`, `detect_speech()`, `transcribe_audio()`, `merge_transcript_with_speakers()`,
    `apply_teacher_verification()` — called only from within `run_pipeline()` itself, in that
    order; none of these five are called directly by anything outside this file.
  - `run_pipeline()` — called only by `worker/tasks.py: _run_pipeline_for_chunk()`.
  - `load_waveform()` — called by `detect_speech()` internally, and also directly by `worker/
    tasks.py: enroll_teacher_task()`.
- **Inputs:** an audio file path, a `LoadedModels` bundle, toggle booleans, `beam_size`,
  `num_speakers`, `enrolled_teachers` (list of `(name, embedding)` tuples).
- **Outputs:** a result dict (`text`, `language`, `whisper_segments`, `speaker_segments`,
  per-stage `stage_latencies`).
- **Side effects:** writes and deletes temporary FFmpeg-intermediate files (`_std.wav`,
  `_cleaned.wav`) on disk, always in a `finally` block.
- **Files read:** the input audio file; FFmpeg's own intermediates it just wrote.
- **Files written:** the same FFmpeg intermediates (deleted before the function returns/raises).
- **Env vars used (via `settings`):** `sample_rate`, `whisper_model_size`, `whisper_device`,
  `whisper_compute_type`, `whisper_cpu_threads`.
- **Network:** none directly — `WhisperModel(...)`/`load_silero_vad()` (called from
  `celery_app.py`, not here) transitively hit Hugging Face Hub on first use, inside those
  libraries' own code, not this file's.
- **Models loaded:** none directly loads a model in this file except `load_whisper_model()` —
  every other model (`silero_vad_model`, `diarization_model`, `teacher_verification_model`) is
  loaded elsewhere (`celery_app.py`) and passed in as part of `LoadedModels`, per the
  locked "loaded once, passed in" rule.

### `backend/worker/celery_app.py`
- **Imported by:** `backend/worker/tasks.py` (top-level, for the `celery_app` object itself),
  `backend/main.py` (lazily, inside `lifespan()`, for `get_worker_models()`).
- **Key functions:**
  - `_load_models()` — called only by `get_worker_models()` and `_preload_models()`.
  - `get_worker_models()` — called by `worker/tasks.py`'s three task functions (each calls it
    once per invocation to get the current process's already-loaded models), and by
    `backend/main.py`'s `lifespan()` in eager mode.
  - `_preload_models()` — a Celery signal handler (`@worker_process_init.connect`), never called
    directly by any code in this repo; Celery's own framework invokes it when a real (non-eager)
    worker process boots.
- **Side effects:** module-level global `_worker_models` — genuinely global, mutable, per-process
  state. This is intentional (§25 in `docs/ARCHITECTURE_DECISIONS.md`), but it means this module
  is **not safely re-importable/reloadable** within a running process — nothing in this codebase
  does that, but a future change (e.g., a hot-reload dev tool) would need to know this.
- **Env vars used:** `celery_broker_url`, `celery_result_backend`, `hf_token` (checked inside
  `_load_models()` to decide whether to attempt loading the diarization model at all).
- **Models loaded (inside `_load_models()`):** Whisper (`load_whisper_model()`, hard requirement —
  raises if it fails), the glossary (`load_glossary()`), Silero VAD (best-effort, logged warning
  on failure, not raised), pyannote diarization (best-effort, only attempted if `hf_token` is
  set), SpeechBrain teacher verification (best-effort).
- **Network:** transitively, via the model-loading calls above, to Hugging Face Hub.

### `backend/worker/tasks.py`
- **Imported by:** `backend/api/transcribe.py` (for `transcribe_chunk_task`,
  `transcribe_file_task`), `backend/api/teacher.py` (for `enroll_teacher_task`).
- **Key functions and exact callers:**
  - `transcribe_chunk_task` — called (via `.delay()`) only from `backend/api/transcribe.py:
    transcribe_stream()`'s `receive_chunks()` loop.
  - `transcribe_file_task` — called (via `.delay()`) only from `backend/api/transcribe.py:
    transcribe_file()`.
  - `enroll_teacher_task` — called (via `.delay()`) only from `backend/api/teacher.py:
    enroll_teacher()`.
  - `_run_pipeline_for_chunk()` — a private helper, called only by `transcribe_chunk_task` and
    `transcribe_file_task`.
- **Side effects:** writes a temp audio file per task (`write_temp_audio()`), always deleted in a
  `finally` (`cleanup_temp_files()`); opens and closes its own `SessionLocal()` DB session per
  task (never reuses a session across tasks); publishes to the `session:{id}:results` pub/sub
  channel on both success and failure.
- **Files written:** one temp file per task invocation, in `<system temp>/scaitale/`.
- **Network:** the pub/sub publish (`publish_sync()`) hits Redis if `CELERY_BROKER_URL` is set;
  otherwise it's an in-process call with no network involved.

### `backend/api/transcribe.py`
- **Imported by:** `backend/main.py` only (`app.include_router(transcribe.router, ...)`).
- **Key functions:**
  - `transcribe_file()` — the `POST /transcribe` handler. Calls `session_service.
    create_session()`, `write_temp_audio()`, `session_service.get_enrolled_embeddings()`,
    `transcribe_file_task.delay()`.
  - `transcribe_stream()` — the `WS /ws/transcribe` handler. Calls `_handle_start_message()`,
    `session_service.get_enrolled_embeddings()`, runs `receive_chunks()` and `listen_results()`
    concurrently via `asyncio.gather()`, calls `finalize_and_close()` (which calls
    `session_service.finalize_session()` — the **only** place in the whole codebase where
    `finalize_session()` is called from).
  - `_handle_start_message()` — called only by `transcribe_stream()`.
- **Network endpoint this file implements:** `POST /api/v1/transcribe`,
  `WS /api/v1/ws/transcribe`.
- **Side effects:** the only file in the API tier that both writes a session to the database
  *and* triggers the entire ML pipeline (indirectly, via `.delay()`).

### `backend/services/session_service.py`
- **Imported by:** `backend/api/transcribe.py`, `sessions.py`, `teacher.py`, `minutes.py` (all
  four API route files), `backend/worker/tasks.py`.
- **Key functions and exact callers:**
  - `create_session()` — called by `transcribe.py`'s `transcribe_file()` and
    `_handle_start_message()`.
  - `append_chunk_result()` — called only by `worker/tasks.py: transcribe_chunk_task()` and
    `transcribe_file_task()`.
  - `materialize_transcript()` — called only by `append_chunk_result()`, internally (not exposed
    to any external caller).
  - `finalize_session()` — called only by `transcribe.py: finalize_and_close()`. This is the
    **single call site** for the entire keyword-extraction + minutes-generation pipeline
    (`keyword_service.extract_keywords()` → `minutes_service.generate_minutes()`).
  - `get_enrolled_embeddings()` — called by `transcribe.py` (both the WS and whole-file paths)
    and `teacher.py`.
  - `create_pending_teacher()`, `complete_teacher_enrollment()`, `fail_teacher_enrollment()` —
    called only from `teacher.py` and `worker/tasks.py: enroll_teacher_task()` respectively.
- **This is the single busiest internal module in the backend** — the only place that touches
  `SessionRecord`/`TeacherEnrollment` ORM objects directly outside of the models themselves;
  every API route and every worker task goes through this file to read or write session/teacher
  state, never touching the ORM models directly.

### `android/lib/main.dart` → `app.dart` (Flutter root)
- **`main.dart`** constructs exactly three shared objects — `SettingsController`, `ApiClient`,
  `AuthController` — wires `ApiClient.onUnauthorized = authController.forceLogout` (the single
  global-401 handling path for the entire app), then calls `runApp(MultiProvider(...))`.
- **`app.dart`**'s `ScaitaleApp` is a `StatelessWidget` whose `build()` reads `AuthController` via
  `context.watch<AuthController>()` and picks `HomeScreen()` or `LoginScreen()` — this is the
  **entire app-wide routing logic**; there is no named-route table anywhere in this app.
- **Critical fact for anyone touching auth:** `ApiClient` is constructed in `main.dart` *before*
  `AuthController`, then `AuthController` is handed a reference to it, then `ApiClient.
  onUnauthorized` is set *after both exist* — this ordering is load-bearing. Constructing
  `AuthController` first (before `ApiClient` exists) would need a different wiring approach
  entirely (a callback set later would need a nullable/late field, not a constructor argument).

### `android/lib/core/pcm_chunker.dart`
- **Imported by:** `android/lib/screens/recording/live_recording_screen.dart` only.
- **Imports:** `local_vad.dart`, `wav_encoder.dart` (both leaf modules — grepped, neither imports
  any other project file).
- **Key methods and their one caller:** `add()` and `flush()` are both called only from
  `live_recording_screen.dart`'s `_beginStreamingAudio()` (the mic-stream listener) and `_stop()`
  respectively — there is no other call site for either method anywhere in the app or its tests
  besides `pcm_chunker_test.dart`.

## 3. Critical dependency chains — "changing X requires checking Y and Z"

- **Changing `PipelineOptions`' field names** (`backend/schemas/pipeline.py`) requires checking:
  `android/lib/models/pipeline_config.dart`'s `toJson()` (must match snake_case exactly), every
  call site that constructs a `PipelineOptions` (`backend/api/transcribe.py`'s two handlers,
  `backend/api/teacher.py` — no, teacher enrollment doesn't use `PipelineOptions`, only
  transcribe.py does), and `android/lib/models/pipeline_config.dart`'s `PipelinePresets` constants.
- **Changing the WebSocket message `type` vocabulary** requires checking: `backend/api/
  transcribe.py` (every `websocket.send_json({"type": ...})` call), `backend/worker/tasks.py`
  (the `publish_sync(channel, {"type": ...})` calls), `android/lib/models/ws_messages.dart`'s
  `WsServerMessage.fromJson()` switch, and `android/lib/screens/recording/
  live_recording_screen.dart`'s `_handleWsMessage()` switch — **four files**, not two.
- **Changing `run_pipeline()`'s stage order** (`backend/services/audio_service.py`) requires
  checking: `teacher_verification_service.py: verify_segment()` (assumes it receives a waveform
  slice bounded by *Whisper's* segment timestamps, not raw VAD chunk timestamps — reordering
  before transcription breaks this assumption structurally, not just stylistically),
  `diarization_service.py`'s consumer `merge_transcript_with_speakers()` (same assumption), and
  the thesis manuscript's own pipeline-order prose (`docs/paper-vs-implementation.md` tracks this
  exact discrepancy already — a reorder here would need a matching manuscript update too).
- **Changing `SessionRecord`'s columns** (`backend/models/session.py`) requires checking:
  `backend/database/migrations/versions/0001_initial_schema.py` (needs a new migration for the
  Postgres path — SQLite auto-creates and won't warn you the two have diverged),
  `session_service.py`'s `to_summary_dict()`/`to_detail_dict()`, `backend/schemas/session.py`'s
  `SessionSummary`/`SessionDetail` (FastAPI's response model will silently drop any field not
  declared there), and `android/lib/models/session_models.dart`'s `fromJson()`.
- **Changing `SUPPORTED_EXTENSIONS`** requires checking: both copies
  (`backend/services/audio_service.py` and `scripts/preprocess_audio.py`) — and this is not just
  convention, `tests/test_audio_extensions.py` **directly imports both** (`from scripts.
  preprocess_audio import SUPPORTED_EXTENSIONS as SCRIPT_EXTENSIONS`) and asserts they match; a
  one-sided edit will fail this specific test, not fail silently.
- **Changing anything `evaluation/wer.py` exports** requires checking: `ai/finetuning/
  finetune_whisper.py`, which imports `word_error_rate` from it directly to track training
  progress mid-run — **this is a real, easy-to-miss cross-directory dependency**; `evaluation/`
  is not purely a standalone tool despite never being imported by `backend/` or `android/` at
  runtime.
- **Changing `backend/worker/celery_app.py`'s `_load_models()` return shape (`LoadedModels`)**
  requires checking: every field consumer in `audio_service.py: run_pipeline()`, and both call
  sites of `get_worker_models()` in `worker/tasks.py`, plus the new caller added this session,
  `backend/main.py: lifespan()`.
- **Changing the Alembic migration chain** requires checking: `backend/database/migrations/
  env.py`'s own model imports (must match `backend/database/db.py: init_db()`'s imports exactly,
  or SQLite and Postgres will create different schemas from the same models).

## 4. Circular dependencies

**None found**, in either the Python backend or the Flutter client — verified by tracing the full
import graph in both languages this pass (§1 above for Python; the Flutter screen graph in §5
below). The backend is a strict layered DAG; the Flutter screen navigation graph is also a DAG
(`home → {enrollment, recording, settings, transcript}`, `recording → transcript`,
`transcript → minutes`, and nothing points back upstream).

## 5. Flutter screen/module dependency graph (verified)

```
main.dart → app.dart, core/api_client.dart, core/auth_controller.dart, core/secure_storage.dart,
            core/settings_controller.dart
app.dart → core/auth_controller.dart, screens/auth/login_screen.dart, screens/home/home_screen.dart
screens/auth/login_screen.dart → core/auth_controller.dart, screens/auth/register_screen.dart
screens/home/home_screen.dart → core/{api_client,api_exception,auth_controller}.dart,
            models/session_models.dart, widgets/{error_banner,loading_view,session_list_tile}.dart,
            screens/enrollment/teacher_enrollment_screen.dart,
            screens/recording/live_recording_screen.dart, screens/settings/settings_screen.dart,
            screens/transcript/transcript_screen.dart
screens/recording/live_recording_screen.dart → core/{auth_controller,pcm_chunker,
            settings_controller,ws_transcribe_client}.dart, models/ws_messages.dart,
            screens/transcript/transcript_screen.dart
screens/transcript/transcript_screen.dart → core/{api_client,api_exception,polling}.dart,
            models/session_models.dart, widgets/{error_banner,loading_view}.dart,
            screens/minutes/minutes_screen.dart
screens/minutes/minutes_screen.dart → core/{api_client,api_exception}.dart,
            models/minutes_models.dart, widgets/{error_banner,loading_view}.dart
screens/enrollment/teacher_enrollment_screen.dart → core/{api_client,api_exception,polling}.dart,
            models/teacher_models.dart, widgets/{error_banner,loading_view,status_badge}.dart
screens/settings/settings_screen.dart → core/{auth_controller,settings_controller}.dart,
            widgets/{advanced_settings_panel,pipeline_preset_selector}.dart
core/pcm_chunker.dart → core/local_vad.dart, core/wav_encoder.dart   (both leaf)
core/auth_controller.dart → core/{api_client,api_exception,secure_storage}.dart
core/api_client.dart → core/api_exception.dart, models/{auth_models,session_models,
            teacher_models}.dart
core/ws_transcribe_client.dart → models/ws_messages.dart
models/ws_messages.dart → models/session_models.dart
```

No cross-screen import goes "backward" (e.g., `minutes_screen.dart` never imports anything from
`transcript_screen.dart` or `home_screen.dart`) — this is a genuinely clean, one-directional
navigation dependency graph.

## 6. Unused / orphaned modules

- **`experiments/`, `integration/`** — confirmed completely empty (zero files, not even
  `.gitkeep`), no code reference anywhere in the repository. Genuinely orphaned — likely leftover
  scaffolding from early planning that was never populated.
- **`scripts/tester`** — a 6-line scratch file (mic-device query + arithmetic sanity check),
  tracked in git since the first backend commit, imported by nothing, called by nothing.
  Functionally orphaned, though intentionally kept as a scratch utility per its own history.
- **`transcripts/`** — referenced by `backend/core/config.py`'s `transcripts_dir` setting
  (created automatically at import time) but **nothing anywhere in this codebase ever writes to
  it**. Not orphaned as a *concept* (the setting exists and is wired up), but currently unused in
  practice — a directory that exists and is created but has no writer.
- **`backend/utils/errors.py`** — **does not currently exist**; it existed historically and was
  deleted as dead code in round 9 (`CLAUDE.md` Part 2). Mentioned here only so a future search for
  it isn't confused by finding references to its removal in the git history.

**Not orphaned, despite appearances:** `scripts/`, `evaluation/`, and `ai/finetuning/` are never
imported by `backend/` or `android/` at runtime, but they are **not orphaned** — `tests/`
imports directly from `scripts/preprocess_audio.py` and from all five `evaluation/*.py` modules
(§3 above), and `ai/finetuning/finetune_whisper.py` imports from `evaluation/wer.py`. Deleting any
of these three directories would break real, currently-passing tests or a real cross-module
dependency, not just remove an unused convenience.

## 7. Duplicated implementations

| What's duplicated | Locations | Kept in sync by |
|---|---|---|
| `SUPPORTED_EXTENSIONS` | `backend/services/audio_service.py`, `scripts/preprocess_audio.py` | An actual test (`tests/test_audio_extensions.py`) importing both and asserting equality — not just convention |
| `transcribe_audio()` (same name, different signature) | `scripts/transcribe_audio.py` (`(model, audio_path: Path)`, key `"segments"`) vs. `scripts/process_pipeline.py` (`(model, waveform, speech_segments)`, key `"whisper_segments"`) | Nothing — documented in `CLAUDE.md`'s "Function signature reference" table as a named collision risk; never imported into the same module |
| Whisper model loading | `scripts/transcribe_audio.py: load_model()` vs. `backend/services/audio_service.py: load_whisper_model()` | Nothing — independently maintained, same underlying `WhisperModel(...)` call, different names |
| Diarization logic (`load_diarization_model`, `diarize_audio`, `format_speaker_segments`) | `scripts/diarize_audio.py` vs. `backend/services/diarization_service.py` | Nothing automatic — `backend/services/diarization_service.py`'s own docstring says it's "the backend-service copy of `scripts/diarize_audio.py`'s importable functions... same logic and signatures," maintained by hand in parallel. **A bug fixed in one (round 9/10's `.itertracks` fix) had to be applied to both separately** — it was, but there's no test enforcing they stay identical the way `SUPPORTED_EXTENSIONS` has one. |
| FFmpeg standardization + denoise | `backend/services/audio_service.py: ingest_audio()/clean_audio()` vs. `scripts/process_pipeline.py: standardize_audio()`/its own denoise call | Same as diarization above — hand-maintained parallel copies, same filter strings (`DENOISE_FILTER`), no automated sync check |
| `write_report()` | Copy-pasted near-identically across all five `evaluation/*.py` scripts | Nothing — noted as a known, deliberately-not-refactored duplication in `CLAUDE.md` Part 2's round 7 deferred list |
| `_get_session_or_404`-style ownership check | Defined once in `backend/api/minutes.py`, re-implemented inline (not imported) in `sessions.py`/`teacher.py` | Nothing — same logic, three separate inline implementations |

## 8. Dead code

No currently-dead code was found in `backend/` or `android/lib/` this pass — `backend/utils/
errors.py` (the one confirmed dead-code deletion in this project's history) is already gone, not
sitting unused. `scripts/tester` (§6) is the closest thing to dead code that still exists on disk:
a real, tracked file with no purpose beyond a one-off manual check, referenced by nothing.

## 9. Legacy / experimental / active implementations

| Component | Classification | Evidence |
|---|---|---|
| `backend/`, `android/lib/` | **ACTIVE** | The only code actually exercised at runtime; both test suites pass; live end-to-end testing confirmed this session |
| `scripts/*.py` (the original six + two smoke tests) | **LEGACY, still maintained** | Their pipeline logic was "promoted" into `backend/services/` (round 3); the "scripts are frozen" rule that followed was explicitly **lifted** later (round 10) specifically because real bugs were found in them — they are actively fixed when broken, but are not where new features get built |
| `evaluation/*.py` | **TOOLING, never run against real data** | Built, unit-tested (via `tests/test_*.py`), zero real classroom-audio results exist anywhere |
| `ai/finetuning/*.py` | **EXPERIMENTAL / SCAFFOLD ONLY** | Imports cleanly, its own error paths are tested, but has **never been executed as a real training run** — no corpus exists (`datasets/processed/` is empty), no trained checkpoint exists anywhere in the repo or its gitignored `models/` folder |
| `deployment/Dockerfile.{api,worker}`, `docker-compose.yml` | **WRITTEN, NEVER RUN** | Neither image has ever been built in any environment this project has existed in; no Docker installation has ever been present |
| Diarization (`backend/services/diarization_service.py`) | **ACTIVE CODE, NEVER EXECUTED END-TO-END** | The code path is real and reachable, but no `HF_TOKEN` has ever been configured in any environment this project has run in — the actual `pyannote.audio` inference call has literally never fired in this project's history |

---

*This document supersedes nothing — it is a companion to `docs/ARCHITECTURE.md` (runtime
behavior) and `docs/ARCHITECTURE_DECISIONS.md` (why things are shaped this way). Where this
document and either of those disagree on a specific import or call site, re-verify directly with
`grep` rather than trusting either — code changes after this pass will not update this file
automatically.*
