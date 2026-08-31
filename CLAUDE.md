# CLAUDE.md — Scaitale (ScAItale)
> Single source of truth for all AI-assisted development sessions.
> Read this file at the start of every Claude Code session before touching any code.

---

## What This Project Is

**Scaitale** is a thesis prototype: a noise-aware, teacher voice-prioritized multilingual classroom transcription and structured minute generation system for Philippine classrooms. It targets real-world Hiligaynon classroom environments where teachers and students naturally code-switch across **three languages only: Hiligaynon, Filipino (Tagalog), and English**.

**Full thesis title:** *"Development and Evaluation of a Noise-Aware Code-Switching Multilingual Speech Recognition and Automated Summarization System for Hiligaynon Classroom Discourse"*

**Repo name:** `academic-discussion-assistant`

---

## Working Dynamic

- **Nathan** = Project Manager. Makes all scope and architecture decisions.
- **Claude** = Primary coder and implementer. Step-by-step execution, no replanning.
- No revisiting locked decisions. Forward momentum only.

---

## Tech Stack (Final, Locked)

| Layer | Technology |
|---|---|
| Client | Flutter (Android-first, thin client) |
| Transport | WebSocket — streaming, chunked (2–5s chunks) |
| Backend | FastAPI |
| Middle layer | `backend/services/audio_service.py` |
| Noise suppression | `pyrnnoise` library (48kHz round-trip via FFmpeg) |
| VAD | Silero VAD |
| Speaker verification | SpeechBrain ECAPA-TDNN (cosine similarity) |
| Diarization | pyannote.audio (optional) |
| Transcription | Faster-Whisper `small`, int8, CPU, multilingual |
| Post-processing | Glossary-based refinement for Hiligaynon/Filipino terms |
| Keyword extraction | TextRank |
| Minutes generation | Rule-based structured output |
| Fine-tuning | LoRA/PEFT on Faster-Whisper small (Hiligaynon corpus) |
| Training platform | Google Colab (free GPU) |

---

## Pipeline Order (Locked)

```
Flutter (WebSocket chunks)
  → FastAPI
    → FFmpeg normalize + loudnorm (ALWAYS ON, never optional)
    → pyrnnoise denoising (48kHz round-trip) [enable_denoise toggle]
    → Silero VAD          [enable_vad toggle]
    → SpeechBrain ECAPA   [enable_teacher_verification toggle]
    → pyannote diarization [enable_diarization toggle, OPTIONAL]
    → Faster-Whisper
    → Glossary refinement
    → TextRank keyword extraction
    → Rule-based minutes generation
    → Storage
    → JSON response → Flutter
```

**Toggle flags:**
- `enable_denoise` — pyrnnoise denoising (opt-in, off by default)
- `enable_vad` — Silero VAD (False = one synthetic whole-file segment returned)
- `enable_diarization` — pyannote (optional/nice-to-have)
- `enable_teacher_verification` — SpeechBrain ECAPA cosine similarity

**Model loading rule:** Both diarization and Whisper models loaded ONCE by the caller, passed in — never reloaded per call.

---

## Repo Structure (Confirmed)

```
academic-discussion-assistant/
├── android/                  # Flutter client only
├── backend/
│   ├── api/
│   ├── services/             # Middle layer between API and AI modules
│   ├── core/
│   ├── database/
│   ├── schemas/
│   ├── models/
│   ├── utils/
│   └── main.py
├── ai/                       # Reusable AI modules (source code only)
│   ├── whisper/
│   ├── rnnoise/
│   ├── silero/
│   ├── pyannote/
│   ├── speechbrain/
│   └── finetuning/
├── models/                   # Trained weights/embeddings only (NO source code)
├── datasets/
│   ├── raw/
│   ├── clean/
│   ├── processed/
│   └── metadata/
├── recordings/
├── transcripts/
├── experiments/              # Per-experiment folders for thesis results
├── evaluation/
│   ├── wer/
│   ├── cer/
│   ├── latency/
│   ├── reports/
│   └── plots/
├── docs/
├── scripts/                  # Dev utilities only, NOT app code
├── tests/
└── deployment/               # Future / Docker
```

**.gitignore must include:** `android/.idea/`
**`license/`** must be a root-level file, not a folder.

---

## Six Built Scripts in `scripts/`

These are dev utilities. Their logic gets promoted into `backend/services/` — not the scripts themselves.

1. `record_test_audio.py` — mic capture → `recordings/classroom.wav` (16000 Hz mono int16)
2. `preprocess_audio.py` — FFmpeg standardization (16kHz mono PCM WAV, loudnorm)
3. `transcribe_audio.py` — Faster-Whisper `small`, int8 CPU, shared `load_model()`
4. `process_pipeline.py` — full pipeline orchestrator with toggle flags; `merge_transcript_with_speakers()` built
5. `simulate_streaming.py` — chunks file into 1–10s pieces (default 3s); full pipeline per chunk
6. `diarize_audio.py` — standalone pyannote pipeline; maps raw labels to Speaker A/B/C by first-appearance

**`process_pipeline.py` logic → `backend/services/audio_service.py`** is the first major backend build task.

---

## Flutter Client — Preset System

- Presets defined **client-side** in `pipeline_config.dart` (backend is stateless)
- Three presets: `Fast / Balanced / Accurate`
- `toJson()` sends concrete parameter values per request — backend never sees preset names
- Beam size = primary speed/accuracy dial
- Chunk duration = Flutter-side slider (1–10s)
- Advanced settings panel with outcome-framed labels

---

## Chunk Duration Constants

- `MIN_CHUNK_DURATION_SECONDS` and `MAX_CHUNK_DURATION_SECONDS`
- Validated **only** in `split_into_chunks()` — single source of truth, not duplicated in argparse

---

## Data Flow

```
Android → FastAPI → Audio Service → RNNoise → Silero → Teacher Verification
→ Diarization → Whisper → Database → JSON → Android
```

---

## Flutter Screens (Required)

1. Home / session library
2. Teacher voice enrollment
3. Live recording + real-time subtitles
4. Transcript view with search and match highlighting
5. Structured minutes view + export
6. Settings (pipeline toggles, preset selector, chunk duration slider)

---

## Evaluation Instrumentation (Built Into Pipeline From Day One)

- Per-chunk latency logged at every pipeline stage
- `evaluation/wer.py` — WER and CER vs reference transcripts
- `evaluation/latency.py` — latency breakdown per stage
- `evaluation/plots/` — metric visualization
- Metrics: WER/CER (by language segment), teacher ID precision/recall/F1, end-to-end latency

---

## Fine-Tuning (IN SCOPE — Non-Negotiable)

- LoRA/PEFT adaptation of Faster-Whisper `small` on Hiligaynon classroom corpus
- Dataset: real classroom recordings by Nathan; naturally occurring Ilonggo code-switched speech
- Format: HuggingFace dataset, 90/10 train/eval split, stored in `datasets/`
- Training: Google Colab free GPU
- Adapters saved to `models/`
- Targeted for second week of September after VAD segmentation + draft transcription by team

---

## Evaluation Metrics (Complete)

- **WER/CER** — overall, AND broken out by language segment (English vs Filipino vs Hiligaynon)
- **Code-switched utterances** — reported separately from monolingual utterances in WER analysis
- **Teacher identification:** precision/recall/F1 AND false-accept/false-reject rate on enrolled vs unenrolled speakers
- **RTF (Real-Time Factor)** — pipeline speed relative to audio duration
- **End-to-end latency** — per pipeline stage
- **Resource usage** — CPU/memory on target hardware
- **Usability** — System Usability Scale (SUS) with actual respondents

---

## Hybrid Edge/Server Design (Architectural Property)

- Local (on-device): VAD + noise suppression — lightweight, always available
- Server (FastAPI): diarization, teacher verification, Whisper transcription
- **Graceful degradation when offline:** local fallback path is an explicit, testable property
- Benchmark full pipeline on actual target hardware in Week 2 — isolate model inference vs integration overhead before FastAPI wiring
- If local pipeline too slow: push diarization/verification to server path, keep VAD+RNNoise local — decide Week 2, not Week 4

---

## Data Collection Tracking (Fine-Tuning Critical Path)

- Weekly hour-target for raw classroom audio = tracked metric, same as WER
- Nathan recording now — phone recorder in classroom is acceptable for raw collection
- If weekly targets not met by Week 6–7, that is the early warning signal
- Explore existing Hiligaynon/Tagalog ASR corpora to reduce cold-start problem
- Transcription by Nathan + Andrei + Dan Joseph (split duty) is the bottleneck, not GPU training

---

## Explicitly Out of Scope (Defensible)

- Training ASR models from scratch
- iOS compatibility
- Full offline mobile deployment
- Cloud infrastructure / production scaling
- Polished UI beyond functional prototype
- Full pyannote diarization (optional, not mandatory)
- **Kinaray-a** — explicitly considered and cut; trilingual scope is final
- Deferred features tracked in `future_ideas.md` at repo root — ideas go there, not into scope

---

## Language Scope (CRITICAL)

**TRILINGUAL ONLY: Hiligaynon, Filipino, English.**
- "Quadrilingual" anywhere in code, comments, or docs is an ERROR.
- Filipino is the correct designation (not "Tagalog") in academic/manuscript contexts.
- Language order in manuscript: Hiligaynon – Filipino – English (standardized).

---

## Key Architectural Rules

1. FFmpeg preprocessing is ALWAYS ON — never toggleable
2. All subsequent pipeline stages have independent toggles
3. Models loaded once by caller, passed in — never reloaded per call
4. Backend is stateless — receives concrete parameter values, not preset names
5. WebSocket transport from day one — not HTTP POST with polling
6. Single source of truth for chunk validation: `split_into_chunks()` only
7. `process_pipeline.py` is the script whose logic promotes into `audio_service.py`

---

## Development Environment

- **OS:** Windows (PowerShell)
- **Project path:** `C:\Users\natha\OneDrive\Documents\Thesis\academic-discussion-assistant\`
- **Virtual environment:** `.venv` in project root — activate before every session
- **FFmpeg:** installed at `C:\ffmpeg\bin`, on PATH — `ffmpeg` and `ffprobe` both available
- **HF_TOKEN:** required for pyannote (Hugging Face gated model) — set per session with `$env:HF_TOKEN = "your_token"` or permanently via `setx`
- **Python standard:** no argparse or CLI concerns inside importable functions — CLI entry points are thin wrappers only

---

## Importable Functions (from `scripts/` → future `backend/services/`)

From `preprocess_audio.py`:
- `check_dependencies()` — confirms ffmpeg/ffprobe on PATH
- `validate_input_file(input_path)` — rejects missing or unsupported files
- `inspect_audio(input_path)` → dict — ffprobe metadata extraction
- `preprocess_audio(input_path, output_path)` → Path — FFmpeg standardization

Output of preprocessing: `recordings/lecture_preprocessed.wav`

From `record_test_audio.py`:
- `sd.PortAudioError` wrapped in `main()` — mic failure gives clean message, not raw traceback
- Same error-handling pattern should be applied to FastAPI upload endpoints later

From `process_pipeline.py` CLI flags (for reference):
- `--no-vad` — disables Silero VAD
- `--diarize` — enables pyannote diarization

### Teacher verification slot (unbuilt — critical path)
- Slots in after diarization in `process_pipeline()`
- Will use its own `enable_teacher_verification` flag
- Compares each speaker cluster against enrolled ECAPA embedding via cosine similarity
- `process_pipeline()` signature will gain `teacher_embedding` and `enable_teacher_verification` params
- SpeechBrain ECAPA-TDNN: enrollment endpoint stores embedding, per-chunk cosine similarity scoring, binary teacher/non-teacher label on each segment

---

### RNNoise — actual implementation
- Uses `pyrnnoise` library, **NOT** FFmpeg `arnndn` filter
- Requires a 48kHz round-trip: upsample (ffmpeg) → `RNNoise.denoise_wav()` → downsample back to 16kHz (ffmpeg)
- `RNNOISE_SAMPLE_RATE = 48000`, `SAMPLE_RATE = 16000`
- Two temp files created (`_48k.wav`, `_48k_denoised.wav`) and cleaned up after
- `pyrnnoise` must be installed: `pip install pyrnnoise`
- `enable_denoise=False` (default) — opt-in, not opt-out

### Waveform loading — soundfile not torchaudio
- `_load_waveform()` uses `soundfile` (`sf.read()`) instead of `silero_vad`'s `read_audio()`
- Reason: `read_audio()` pulls in torchaudio's torchcodec backend which requires FFmpeg shared DLLs — not the same as the ffmpeg/ffprobe executables already on PATH (Windows-specific conflict)
- Returns `torch.Tensor` (float32) from numpy array

### Function name collision — CRITICAL
- `transcribe_audio()` exists in **two places** with **different signatures:**
  - `transcribe_audio.py` → takes `(audio_path: Path)` — standalone script version
  - `process_pipeline.py` → takes `(model: WhisperModel, waveform: np.ndarray, speech_segments: list[dict])` — pipeline version
- Never import both into the same module without aliasing

### Whisper segment output fields
Each segment in `whisper_segments` contains:
- `start`, `end` (seconds, float)
- `text` (string)
- `avg_logprob` (float) — confidence proxy, useful for filtering hallucinations
- `no_speech_prob` (float) — silence/hallucination detector
- `speaker` (string, added by merge step) — "Unknown" if no diarization overlap

### process_pipeline.py CLI flags (complete)
- `audio_file` — positional, path to preprocessed 16kHz mono WAV
- `--denoise` — enable RNNoise (off by default)
- `--no-vad` — skip Silero VAD
- `--diarize` — enable pyannote diarization
- `--hf-token` — Hugging Face token (or set `HF_TOKEN` env var)
- `--num-speakers` — optional, exact speaker count if known

### diarize_audio.py — key details
- Pipeline: `pyannote/speaker-diarization-community-1`
- Raw output extracted to plain `(start, end, raw_label)` tuples immediately — downstream is library-agnostic
- Speaker labels mapped by first-appearance order: `_letter_for_index()` handles A→Z then AA, AB...
- `run_diarization()` orchestrates load → diarize → format (same shape as `process_pipeline()`)
- Importable functions used by `process_pipeline.py`: `load_diarization_model()`, `diarize_audio()`, `format_speaker_segments()`

### simulate_streaming.py — key details
- Chunk files written as int16 WAV to `{input_stem}_chunks/` subdirectory inside `recordings/`
- Growing transcript built by appending chunk text with space separator
- Cross-chunk speaker continuity explicitly absent — speaker clustering restarts per chunk (documented caveat, not a bug — real fix needs a running known-speakers approach in the backend)
- `DEFAULT_CHUNK_DURATION_SECONDS = 3.0`
- CLI flag: `--chunk-seconds` (not `--chunk-duration`)

### transcribe_audio.py — key details
- `load_model(model_size="small", device="cpu", compute_type="int8")` — shared importable function
- `transcribe_audio(model, audio_path: Path)` — standalone version, takes a path not a waveform
- Output key is `"segments"` (not `"whisper_segments"` — different from process_pipeline.py version)
- `print_results()` is a separate display-only function — not coupled to transcribe logic
- `segments` generator from faster-whisper consumed immediately with `list()` — not lazy

### Function signature reference (CRITICAL — avoid collision)

| Function | File | Signature |
|---|---|---|
| `load_model` | `transcribe_audio.py` | `(model_size, device, compute_type) → WhisperModel` |
| `transcribe_audio` | `transcribe_audio.py` | `(model, audio_path: Path) → dict` with `"segments"` key |
| `transcribe_audio` | `process_pipeline.py` | `(model, waveform: np.ndarray, speech_segments: list) → dict` with `"whisper_segments"` key |
| `load_diarization_model` | `diarize_audio.py` | `(hf_token: str) → Pipeline` |
| `diarize_audio` | `diarize_audio.py` | `(pipeline, audio_path, num_speakers) → list[tuple]` |
| `format_speaker_segments` | `diarize_audio.py` | `(raw_segments: list[tuple]) → list[dict]` |
| `run_diarization` | `diarize_audio.py` | `(audio_path, hf_token, num_speakers) → dict` |
| `merge_transcript_with_speakers` | `process_pipeline.py` | `(whisper_segments, speaker_segments) → list[dict]` |
| `process_pipeline` | `process_pipeline.py` | `(input_path, whisper_model, enable_*, diarization_model, num_speakers) → dict` |
| `split_into_chunks` | `simulate_streaming.py` | `(input_path, chunk_duration_seconds) → list[Path]` |
| `simulate_streaming` | `simulate_streaming.py` | `(input_path, whisper_model, chunk_duration_seconds, enable_*, diarization_model) → dict` |
| `inspect_audio` | `preprocess_audio.py` | `(input_path: Path) → dict` |
| `preprocess_audio` | `preprocess_audio.py` | `(input_path, output_path) → Path` |

## Known Open Issues

- Flutter WebSocket integration: **unbuilt** — Nathan is building the Flutter screens next; backend endpoints are ready for them to call
- Per-chunk diarization has no cross-chunk speaker continuity (restarts each chunk) — unchanged, still true for streamed WS chunks
- Ethics/consent clearance for classroom recordings — must resolve before September recordings
- Whisper first-segment language lock on code-switched speech — known artifact, accepted
- Single-pass loudnorm (vs two-pass FFmpeg) — known limitation, accepted
- `backend/data/glossary.json` is a starter/example list only, not derived from real Whisper error logs yet — grow it from the September corpus pass
- Teacher-verification cosine threshold (`backend/core/config.py: teacher_verification_threshold`) is a reasonable default, not empirically calibrated — `evaluation/teacher_id.py` exists to score it, but needs real enrolled-vs-unenrolled labeled data to run against
- Minutes generation is a documented heuristic (time-gap topic grouping + trigger-phrase action items), not NLP — expect misses on real classroom audio
- Fine-tuning (`ai/finetuning/`) is a complete, tested-importable scaffold, not a trained model — it has no corpus to train on yet (`datasets/processed/` is empty pending the team's recording + transcription pass) and has never actually been run end-to-end
- SUS scoring (`evaluation/sus.py`) has no respondents yet — it's the scoring math only, per CLAUDE.md's "with actual respondents" still needing actual respondents
- Docker/Postgres/Redis are not installed in this dev sandbox — `deployment/` and `backend/database/migrations/` are written to spec and covered by CI, but not run-verified in this session; a green `.github/workflows/ci.yml` run after push is the actual confirmation
- `POST /transcribe`'s whole-file path assumes the API and worker containers share a filesystem/volume (see `deployment/docker-compose.yml`'s `shared-tmp` volume) — object storage (S3-compatible) is the properly distributed fix, not yet built (no infra here to build it against)
- No load testing has been done — the worker-pool/async rearchitecture is correct-by-construction and unit/integration tested, but its actual throughput under concurrent load is unmeasured

**Resolved this pass** (were unbuilt, now built — see "Backend (Built)" below): SpeechBrain ECAPA teacher verification, FastAPI endpoints (POST + WebSocket), transcript persistence, glossary post-processing, TextRank + rule-based minutes, `evaluation/wer.py` + `evaluation/latency.py`.

**Resolved this pass, round 2** (beyond the 14-day list, rest of CLAUDE.md's "Evaluation Metrics (Complete)"): `evaluation/teacher_id.py` (precision/recall/F1, FAR/FRR), `evaluation/sus.py` (SUS scoring), `evaluation/resources.py` (CPU/memory via psutil), and the `ai/finetuning/` LoRA/PEFT scaffold (train + merge/convert-to-CTranslate2) for the "Non-Negotiable" fine-tuning item.

**Resolved this pass, round 3** (production/market-deployment architecture — see "Production Architecture" below): the blocking-event-loop bug (API/worker split via Celery), auth (JWT), Postgres + Alembic migrations, structured logging + Prometheus metrics + optional Sentry, rate limiting + upload-size limits, API versioning (`/api/v1`), consent/deletion (RA 10173 basics), Docker images + docker-compose + CI.

**Round 3 — production/market-deployment rearchitecture** (explicit scope change past CLAUDE.md's original "no production scaling" boundary, at the user's request after an architecture review): see "Production Architecture" below. This is a real rearchitecture, not additive — `backend/main.py` no longer loads any ML models, `POST /transcribe` is now async (202 + poll), and every route requires auth. The bullets right below this describe the CURRENT shape; treat mentions of "SQLite" or "synchronous" pipeline calls elsewhere in this file as historical unless a bullet here says otherwise.

---

## Backend (Built)

Everything below lives in `backend/` and `evaluation/`, promoted from the six scripts per CLAUDE.md's rule (scripts themselves untouched).

- **`backend/services/audio_service.py`** — the pipeline orchestrator, unchanged by the Round 3 rearchitecture (only *what calls it* changed — see "Production Architecture"). Adds one thing `process_pipeline.py` never actually did: FFmpeg preprocessing now runs unconditionally on every chunk/file (`ingest_audio()`), closing the gap between the locked "always on" rule and what the script actually executed. Denoise/VAD/diarization/teacher-verification stay independently toggleable. Per-stage latency recorded on every call.
- **`backend/services/teacher_verification_service.py`** — SpeechBrain ECAPA-TDNN (`spkrec-ecapa-voxceleb`), cosine similarity against enrolled embeddings, lazy-imported the same way `pyrnnoise` already was so a missing install degrades gracefully instead of crashing the worker.
- **`backend/services/glossary_service.py`** + **`backend/data/glossary.json`** — case-preserving glossary correction, applied per-chunk right after transcription.
- **`backend/services/keyword_service.py`** — TextRank on `networkx` (no nltk/sumy), trilingual stopword list.
- **`backend/services/minutes_service.py`** — rule-based topics/key-points/action-items/participants, run once per session at finalize.
- **`backend/database/`, `backend/models/`** — Postgres via SQLAlchemy + Alembic migrations (SQLite by default locally/in tests — see "Production Architecture"). One denormalized `sessions` row per recording (JSON columns for segments/keywords/minutes, `owner_id`-scoped) and one `teacher_enrollments` row per enrolled teacher (also `owner_id`-scoped). A new `users` table backs login.
- **`backend/api/`** (all mounted under `/api/v1`, all requiring a bearer token) — `POST /transcribe` (async: 202 + enqueue, client polls `GET /sessions/{id}`) and `WS /ws/transcribe` (`?token=` query param; `start` JSON control frame → binary WAV chunk frames → `end` JSON control frame, mirroring `simulate_streaming.py`'s growing-transcript pattern over the wire, now via a worker pool + pub/sub fan-out instead of running inline); `GET /sessions`, `GET /sessions/{id}`, `DELETE /sessions/{id}` (session library + transcript view + RA 10173 purge); `POST /teachers/enroll` (also async), `GET /teachers`, `GET /teachers/{id}`, `DELETE /teachers/{id}`; `GET /sessions/{id}/minutes`, `GET /sessions/{id}/minutes/export` (markdown/txt download); `POST /auth/register`, `POST /auth/login`.
- **`evaluation/wer.py`** — WER/CER via from-scratch edit distance (no `jiwer`), with a by-group breakdown hook for language/code-switching splits.
- **`evaluation/latency.py`** — aggregates the `stage_latencies` every pipeline call already returns, computes RTF, writes JSON reports + a matplotlib bar chart.
- **`evaluation/teacher_id.py`** — precision/recall/F1 + false-accept/false-reject rate from labeled (predicted, actual) segment pairs.
- **`evaluation/sus.py`** — standard 10-item System Usability Scale scoring + Bangor/Kortum/Miller adjective bands; scoring math only, needs real respondent data.
- **`evaluation/resources.py`** — CPU/memory sampling (via `psutil`) around any pipeline run.
- **`ai/finetuning/`** — LoRA/PEFT fine-tuning of `openai/whisper-small` (`finetune_whisper.py`) + merge-and-convert-to-CTranslate2 (`convert_to_faster_whisper.py`) so a fine-tuned model drops straight into `backend/services/audio_service.load_whisper_model()` via `WHISPER_MODEL_SIZE`. Imports clean and its error paths are exercised, but it has never trained against real data — see `ai/finetuning/README.md`.
- **`tests/`** — pytest coverage for the pure-logic services (glossary, keywords, minutes, WER, teacher-ID metrics, SUS scoring, resource sampling) — nothing that needs the actual model weights or trained checkpoints.

Search/highlighting in the transcript view is intentionally not a backend endpoint — the full transcript + per-segment timestamps already comes back from `GET /sessions/{id}`, so it's client-side substring matching in Flutter.

---

## Production Architecture (Round 3)

Triggered by an architecture review that found: `async def` routes calling CPU-bound pipeline code synchronously (blocked the whole event loop during transcription — measured RTF > 1, a live bug, not hypothetical), no horizontal scaling story for inference, SQLite/no-migrations, zero auth on any endpoint (including uploading classroom audio), no observability, no containerization/CI, no rate limiting, no privacy/consent controls. Closed with standard, well-known patterns — nothing bespoke.

**API / worker split** — the actual fix for the blocking bug. `backend/main.py` is the API tier: FastAPI only, loads no ML models, verified (`import backend.api.transcribe; import backend.api.teacher` — checked against `sys.modules`) to never transitively import torch/faster-whisper/pyannote/silero_vad/speechbrain/pyrnnoise. `backend/worker/celery_app.py` + `backend/worker/tasks.py` are the worker tier: a separate process (`celery -A backend.worker.celery_app worker`) that actually runs `audio_service.run_pipeline()`, with models loaded once per worker process (`worker_process_init` signal — same "loaded once" rule, relocated). `POST /transcribe` returns `202` and enqueues; the client polls `GET /sessions/{id}`. WS chunks are enqueued on receipt (non-blocking) and results come back via `backend/core/pubsub.py` — real Redis pub/sub when `CELERY_BROKER_URL` is set, an in-process `asyncio.Queue` fan-out otherwise (faithful stand-in *only* because `CELERY_TASK_ALWAYS_EAGER` makes the "worker" run inline in that one no-broker case). Tasks are enqueued via imported task objects' `.delay()`, not `celery_app.send_task("name", ...)` — the latter ignores `task_always_eager` entirely (confirmed: logs `AlwaysEagerIgnored` and actually posts to a broker nothing is consuming), which would silently break the whole eager-mode dev/test/CI path. `backend/worker/tasks.py` keeps `audio_service`'s import lazy (inside each task's function body) specifically so the API process importing this module for `.delay()` stays cheap despite that.

**Ordering under a worker pool** — a real risk once chunks can complete out of order (different workers, different completion times): `SessionRecord.chunk_results` (JSON, keyed by chunk index) is the source of truth; `session_service.materialize_transcript()` rebuilds `transcript_text`/`transcript_segments` from the longest *contiguous* prefix starting at index 0, so a chunk landing early never makes text appear out of order in a live transcript, and duration/latency (order-independent sums) still count every completed chunk regardless. Dedicated tests in `tests/test_tasks.py`.

**Auth** — JWT (PyJWT) + `OAuth2PasswordBearer`, FastAPI's own documented pattern. `bcrypt` directly, NOT passlib's `CryptContext` — confirmed passlib 1.7.4 (unmaintained) raises `AttributeError: module 'bcrypt' has no attribute '__about__'` against the bcrypt version this project installs. New `users` table; `sessions`/`teacher_enrollments` gained `owner_id`. WS auth is `?token=` (browser WebSocket API can't set headers).

**DB** — Postgres via Alembic (`backend/database/migrations/`), hand-written initial migration (no live Postgres in this dev sandbox to autogenerate against) — **verified by actually running `alembic upgrade head` + `downgrade base` + `upgrade head` again against SQLite**, confirming the migration itself is correct even though Postgres-specific behavior is only checked in CI. SQLite stays the default when `DATABASE_URL` is unset, so local dev/`pytest` need no infra.

**Observability** — `backend/core/logging.py`: stdlib `logging` + JSON formatter + request-ID contextvar/middleware (no new dependency). `prometheus-fastapi-instrumentator` on `/metrics`. Optional Sentry via `SENTRY_DSN` (no-op unset).

**Rate limiting** — `slowapi` on `/auth/login`, `/transcribe`, `/teachers/enroll` — confirmed live (12 rapid `/auth/login` calls: first 10 returned `401`, 11th and 12th returned `429`). `MaxUploadSizeMiddleware` rejects an oversized `Content-Length` before the body is read.

**Privacy (RA 10173 basics)** — `consent_confirmed: bool` required at session creation (refused otherwise); `DELETE /sessions/{id}` full purge. Raw audio was already never persisted past processing (temp files cleaned up in `finally` blocks, both in the old single-process design and the new task-based one) — that's now called out explicitly as a privacy property.

**Containerization/CI** — `deployment/Dockerfile.api` (lean: `requirements-api.txt` only, no ffmpeg) + `deployment/Dockerfile.worker` (`requirements-worker.txt`, has ffmpeg) + `deployment/docker-compose.yml` (postgres, redis, api, worker, a `migrate` one-shot service, a shared temp volume for `POST /transcribe`'s whole-file path). `.github/workflows/ci.yml` runs the full suite against real postgres+redis service containers. **Neither is runnable in this dev sandbox** (no Docker installed here) — written to spec, not run-verified this session; CI is the actual verification once pushed.

**Known, documented gaps, not oversights**: `POST /transcribe`'s whole-file task takes a filesystem path (assumes API/worker share a volume) rather than base64 bytes like WS chunks do — a full lecture recording is too large to comfortably embed in a broker message; the properly distributed fix is object storage (S3-compatible), left for when real infra exists to build it against. Eager mode's *first* request after a cold start pays the full one-time model-loading cost synchronously and can trip a WS client's keepalive timeout (observed directly in testing) — a real deployment's worker pre-loads models before serving traffic and never blocks the API's event loop regardless, which is the actual point of the split.

---

## Current Build Priority (14-Day Sprint)

1. ~~`backend/services/audio_service.py` — wraps preprocess + transcribe~~ **done**
2. ~~`/transcribe` POST/WebSocket endpoint~~ **done**
3. ~~Silero VAD integration into audio service~~ **done**
4. ~~SpeechBrain ECAPA enrollment + verification service~~ **done**
5. Flutter audio recording → WebSocket → backend round trip
6. Live subtitle display in Flutter
7. Teacher enrollment screen
8. ~~Glossary post-processing~~ **done**
9. ~~TextRank + rule-based minutes generation~~ **done**
10. Minutes screen + export in Flutter
11. ~~Evaluation scripts (`wer.py`, `latency.py`)~~ **done**
12. End-to-end demo recording

Remaining items (5–7, 10, 12) are Flutter/manual-recording work, next up with Nathan building the screens against the endpoints above.

---

*Last updated: August 2026. Maintained by Nathan (PM) + Claude (implementer).*
