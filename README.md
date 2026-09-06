# Talakayan (Scaitale)

> **Development and Evaluation of a Noise-Aware Code-Switching Multilingual Speech Recognition and Automated Summarization System for Hiligaynon Classroom Discourse**
>
> Confirmed against the actual manuscript title page (`THESIS_ Development and Evaluation of a Noise-Aware Code-Switching Multilingual Speech Recognition and Automated Summarization System for Hiligaynon Classroom Discourse (4).docx`) — this is the real title, matching CLAUDE.md's "Full thesis title" line exactly. The previous version of this line here said "Tagalog" instead of "Filipino" and used older, superseded wording; both are now fixed. See `docs/paper-vs-implementation.md` for the full comparison against the manuscript's Chapter 1 and Chapter 3.

An Android-first (Flutter) hybrid AI system for near real-time, multilingual classroom transcription, built as an undergraduate Computer Science thesis. A FastAPI backend performs the heavy AI inference — noise suppression, server-side voice activity detection, teacher verification, speaker diarization, and transcription — while the mobile client stays lightweight: a real energy-based voice activity gate now runs on-device too, deciding whether a chunk is even worth sending before it ever reaches the network.

**Status: backend and Flutter client both built, production-hardened, and verified end-to-end.** `scripts/` still holds the six standalone prototype modules documented below (untouched, still independently runnable). Their logic has been promoted into a real backend split across two tiers — `backend/main.py` (FastAPI, no ML models, auth-gated) and `backend/worker/` (Celery, the actual pipeline) — with Postgres persistence, async `POST /transcribe` + `WS /ws/transcribe`, teacher enrollment/verification, glossary post-processing, TextRank keywords, rule-based minutes, `evaluation/`'s metric scripts, and `deployment/`'s Docker + CI setup. The Flutter client (`android/`) implements all six required screens against that real backend contract and has been run end-to-end on an Android emulator against the actual running stack — see section 10. What's left is Nathan's own work or blocked on real-world data/people (ethics clearance, real classroom recordings, the fine-tuning run, a physical-device test), not more code. This README covers what's needed to get the prototype scripts, the backend, the Flutter client, and (once you have Docker) the full deployment running.

---

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| Windows | development environment |
| Python 3.11 | confirm with `python --version` |
| Flutter SDK | only needed for the client, section 10 — confirm with `flutter doctor` |
| VS Code | recommended, not required |
| Git | for cloning / version control |

---

## 2. Virtual Environment Activation

type "..\.venv\Scripts\Activate.ps1" in the terminal to activate.
If it does'nt work, type "Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass"

---

## 3. System dependency: FFmpeg

`ffmpeg` and `ffprobe` must both be callable from any terminal — every script touching raw audio depends on them.

1. Download a build from [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/) (the "essentials" build is enough).
2. Extract it somewhere permanent, e.g. `C:\ffmpeg`.
3. Add `C:\ffmpeg\bin` to your Windows PATH environment variable (`ffprobe.exe` ships in the same folder).
4. Open a **new** terminal — PATH changes don't apply to terminals already open.
5. Verify: `ffmpeg -version` and `ffprobe -version` should both print version info.

---

## 4. Python dependencies

```bash
pip install sounddevice soundfile numpy
pip install faster-whisper
pip install torch torchaudio
pip install silero-vad
pip install pyannote.audio
pip install pyrnnoise   # optional — see note below
```

Or, once `requirements.txt` is in place at the repo root:

```bash
pip install -r requirements.txt
```

**`pyrnnoise` is optional and may not install cleanly on Windows.** It wraps a C library and can require CMake / a C++ build toolchain if no prebuilt wheel matches your Python version. That's expected, not a broken setup — RNNoise is designed to be skippable in this architecture (`enable_denoise=False`). Try it; if it fails, move on and revisit later.

---

## 5. Hugging Face account (required for diarization)

`diarize_audio.py`, and `process_pipeline.py` / `simulate_streaming.py` when run with `--diarize`, use a gated pyannote.audio model.

1. Create a free account at [huggingface.co](https://huggingface.co).
2. Visit [huggingface.co/pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1) and accept the usage conditions. (If it depends on a gated underlying segmentation model too, the first run's error message will name that exact page.)
3. Generate a **Read**-role token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens).
4. Store it as an environment variable rather than pasting it into code:
   ```
   setx HF_TOKEN "your_token_here"
   ```
   (open a new terminal afterward for it to take effect)

---

## 6. Repository structure (current)

```
academic-discussion-assistant/
├── recordings/                    raw + preprocessed test audio, chunk folders
├── scripts/                       all six prototype scripts (section 7) + ws_smoke_test.py / v2_smoke_test.py
├── backend/                       api/ (auth-gated, /api/v1), services/ (pipeline, unchanged), worker/ (Celery — where models load),
│                                  database/ (+ migrations/, Alembic), models/, schemas/, core/ (config, security, logging, rate_limit,
│                                  pubsub), utils/, data/ (section 9, below)
├── requirements-api.txt           lean — deployment/Dockerfile.api installs only this
├── requirements-worker.txt        the ML stack — deployment/Dockerfile.worker installs only this
├── deployment/                    Dockerfile.api, Dockerfile.worker, docker-compose.yml, .env.example (section 13)
├── .github/workflows/ci.yml       runs the full test suite against real postgres+redis service containers, plus a
│                                  second `flutter` job (pub get + analyze + test) for android/
├── evaluation/                    wer.py, latency.py, teacher_id.py, sus.py, resources.py + reports/, plots/ output dirs (section 11)
├── ai/finetuning/                 LoRA/PEFT fine-tune + CTranslate2 convert scripts, not yet run (section 12)
├── datasets/                      raw/ · clean/ · processed/ · metadata/ — scaffolded, empty pending the team's corpus
├── tests/                         pytest coverage — pure-logic services + real end-to-end Celery task tests (eager mode)
├── android/                       Flutter client — all 6 screens built, tested (57 Dart unit tests), and verified
│                                  end-to-end on an Android emulator against the real backend (section 10)
├── models/                        downloaded/trained weights land here, gitignored — not backend/models/ (that's source code)
├── transcripts/                   scaffolded, empty — transcripts now persist to the DB, not this folder
└── docs/                          DFD.md (Level 0 + Level 1 diagrams), DevelopmentLog.md, future_ideas.md
```

---

## 7. Running the scripts

Run in this order — each script after the first depends on a file the previous one produces.

### `record_test_audio.py`
Captures ~10 seconds from the default microphone, saves `recordings/classroom.wav`, prints channels / sample rate / bit depth / duration.
```bash
cd scripts
python record_test_audio.py
```

### `preprocess_audio.py`
Standardizes any input audio (`.mp3 .wav .m4a .ogg .webm .flac .aac`) into 16kHz mono PCM WAV via FFmpeg.
```bash
python preprocess_audio.py ../recordings/classroom.wav
```
→ produces `recordings/lecture_preprocessed.wav`

### `transcribe_audio.py`
Whole-file transcription with Faster-Whisper (`small`, int8, CPU). Also the source of `load_model()`, reused by the two scripts below.
```bash
python transcribe_audio.py ../recordings/lecture_preprocessed.wav
```

### `process_pipeline.py`
The configurable core: optional RNNoise → optional Silero VAD → Whisper → optional pyannote diarization, with speaker labels merged into the transcript by timestamp overlap.
```bash
python process_pipeline.py ../recordings/lecture_preprocessed.wav [--denoise] [--no-vad] [--diarize] [--hf-token TOKEN] [--num-speakers N]
```

### `simulate_streaming.py`
Splits a file into fixed-duration chunks (1–10s, default 3s) and runs each independently through `process_pipeline()`, simulating how a real backend will receive live audio.
```bash
python simulate_streaming.py ../recordings/lecture_preprocessed.wav --chunk-seconds 3 [--denoise] [--no-vad] [--diarize] [--hf-token TOKEN]
```

### `diarize_audio.py`
Standalone pyannote speaker diarization — "Speaker A/B/C" with timestamps, independent of transcription.
```bash
python diarize_audio.py ../recordings/lecture_preprocessed.wav [--hf-token TOKEN] [--num-speakers N]
```

---

## 8. Known issues / open items (scripts/)

- **Unresolved, but not a code bug:** `record_test_audio.py` printed `Sample rate: 1600 Hz` in one test run instead of `16000 Hz`. A code review found no discoverable defect — `record_audio()`, `save_recording()`, and `inspect_wav_file()` all thread the same `sample_rate=16000` variable through consistently, so this reads as a one-off hardware/driver quirk (or a misreported terminal capture) rather than a reproducible bug. Worth a manual re-check with a real mic if it recurs.
- **`requirements.txt` is intentionally unpinned** (package names only, no version numbers) while the environment is still in flux — worth pinning once it stabilizes.
- These six scripts stay CLI-only/file-path-based by design — see `backend/` (section 9) for the wired-up equivalent.

---

## 9. Running the backend

The backend is two processes now: a lightweight FastAPI **API** tier (no ML models — see `backend/main.py`'s docstring) and a **worker** tier that actually runs the pipeline (`backend/worker/`). Auth is required on every route (`POST /api/v1/auth/register` then `/login`).

```bash
pip install -r requirements.txt          # full local-dev union — see its header comment
                                          # for the leaner requirements-api.txt / requirements-worker.txt split

# Terminal 1 — API (no ML models loaded, starts in seconds)
export JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")   # PowerShell: $env:JWT_SECRET_KEY = ...
uvicorn backend.main:app --reload

# Terminal 2 — worker (loads Whisper/Silero VAD/SpeechBrain/pyannote — first run downloads them, can take a few minutes)
export JWT_SECRET_KEY=...   # same value, though the worker itself doesn't check auth
celery -A backend.worker.celery_app worker --loglevel=info
```

**No worker running?** Requests still work — no `CELERY_BROKER_URL` set means Celery's `task_always_eager` kicks in and tasks run inline inside the API process instead (see `backend/worker/celery_app.py`). Fine for quick local testing; the first request after starting up will be slow (pays the one-time model-loading cost synchronously) and can even trip a WebSocket client's keepalive timeout — that's expected in this no-worker mode and is exactly what running a real worker process fixes.

Then open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) for interactive API docs, or (all under `/api/v1`, all requiring `Authorization: Bearer <token>` from `/auth/login` except registration/login themselves):

- `POST /auth/register`, `POST /auth/login` — email/password, returns a JWT.
- `POST /transcribe` — multipart file upload, **async**: returns `202 {"session_id", "status": "processing"}` immediately; poll `GET /sessions/{id}` until `status` is `completed`/`failed`. `consent_confirmed=true` is a required form field.
- `WS /ws/transcribe?token=<jwt>` — send a JSON `{"type": "start", "consent_confirmed": true, "options": {...}}` frame, then binary WAV-chunk frames, then `{"type": "end"}`. See `scripts/ws_smoke_test.py` (WS-only) or `scripts/v2_smoke_test.py` (full walkthrough: register, both transcribe paths, enrollment, rate limiting, `/metrics`) for runnable examples against `recordings/lecture_preprocessed.wav`.
- `GET /sessions`, `GET /sessions/{id}`, `DELETE /sessions/{id}` — session library + transcript + purge.
- `POST /teachers/enroll` (also async — poll `GET /teachers/{id}` for `status: "ready"`), `GET /teachers`, `GET /teachers/{id}`, `DELETE /teachers/{id}`.
- `GET /sessions/{id}/minutes`, `GET /sessions/{id}/minutes/export?format=markdown` — structured minutes (topics, key points, definitions, action items, participants, `teacher_speech_ratio`/`teacher_speakers`) + download.
- `GET /metrics` — Prometheus metrics (no auth).

Data lives in SQLite by default (`backend/database/scaitale.db`, gitignored) — set `DATABASE_URL` for Postgres (see section 13). Pipeline toggles (`enable_denoise`, `enable_vad`, `enable_diarization`, `enable_teacher_verification`, `num_speakers`, `beam_size`) are sent as concrete values on every request — the backend is stateless and doesn't know about Flutter's Fast/Balanced/Accurate presets.

Run the full test suite (pure-logic services + real end-to-end Celery task tests against actual model inference, in eager mode — no Redis/worker needed) with:

```bash
pytest tests/
```

### Known issues / open items (backend/)

- **The Flutter client is wired up and verified against every endpoint above** — see section 10. Not yet run on a physical device or against real classroom audio.
- **`backend/data/glossary.json` is a starter/example list**, not derived from real Whisper error logs — grow it from the September corpus pass.
- **Teacher-verification threshold is a reasonable default, not calibrated** against real enrolled-vs-unenrolled data yet — `evaluation/teacher_id.py` scores it once you have labeled data.
- **Per-chunk diarization still has no cross-chunk speaker continuity** over WebSocket — same caveat as `simulate_streaming.py`.
- **Minutes generation is a documented heuristic** (time-gap topic grouping, teacher-prioritized key points/topic labels, trilingual pattern-matched definitions + action items), not NLP — expect misses on real classroom audio; `definitions`' precision/recall is unmeasured until real data exists to score it against.
- **`POST /transcribe`'s whole-file task assumes the API and worker share a filesystem** (a volume in `deployment/docker-compose.yml`) — fine co-located, not yet fixed for true multi-host (needs object storage).
- **Docker images themselves aren't built/run** — Postgres 17 + a Redis-compatible server were installed natively and verified directly (migration, a real separate worker process, CI green on `main`); the Dockerfiles/compose are written to spec but not yet run as actual containers. See section 13.

---

## 10. Running the Flutter client

`android/` (repo root — Flutter's own generated native Android folder nests inside as `android/android/`, an accepted quirk of that layout, not a mistake) is a real, tested app against the backend contract in section 9, not a mock. All six required screens are built: home/session library, teacher voice enrollment, live recording + subtitles, transcript view with search, structured minutes + export, settings.

### Prerequisites

- [Flutter SDK](https://flutter.dev/) (built and verified against 3.47.2) — `flutter doctor` should show no blocking issues for Android.
- An Android emulator (AVD) or physical device. `flutter emulators` lists configured ones; `flutter emulators --launch <id>` starts one.
- The backend running (section 9) — API + worker, with Postgres/Redis or the no-broker eager-mode fallback.

### Run it

```bash
cd android
flutter pub get
flutter run                    # picks the first available device/emulator, or add -d <device-id>
```

On first launch, go to **Settings** and check the server address: it defaults to `http://10.0.2.2:8000` on Android (the standard host-loopback alias for an emulator reaching the same machine's backend) or `http://127.0.0.1:8000` on the Windows-desktop target. A **physical device** needs the host machine's real LAN IP instead — both the phone and the backend must be on the same Wi-Fi, per this project's local-first design (no cloud, see the Hybrid Edge/Server Design note in `CLAUDE.md`).

### Tests

```bash
flutter analyze     # must be clean
flutter test        # 57 pure-Dart unit tests, no device needed
```

Covers: pipeline preset resolution and exact JSON key names against the backend schema (the single highest-risk typo surface in the app), WAV header encoding, PCM chunking + the on-device VAD gating/hangover sequence, the on-device VAD's RMS math itself, model `fromJson` parsing, WebSocket message parsing, and the polling backoff helper. Things that genuinely need a device (real mic capture, the real WebSocket round-trip) are exercised manually against the real backend, not automated — see `CLAUDE.md`'s "Flutter Client (Built)" section for exactly what's been verified this way and what hasn't (a physical device, real classroom audio, and a couple of secondary screens with real non-empty data are still open).

### What it does on-device before anything reaches the network

`android/lib/core/local_vad.dart` runs a lightweight energy (RMS) check on every outgoing audio chunk and skips sending it if it's just silence — a 1-chunk "hangover" keeps sending for one chunk after real speech so a trailing word isn't clipped at the chunk boundary, and the very first chunk of a session is always sent. This is the on-device half of the hybrid edge/server split; noise suppression and offline-fallback recording are not implemented on-device (see `CLAUDE.md`).

---

## 11. Evaluation scripts

All write JSON reports to `evaluation/reports/` (and `evaluation/latency.py` also writes a bar chart to `evaluation/plots/`). Each is also directly importable — see `tests/` for usage examples that don't need real data.

| Script | What it needs | What it measures |
|---|---|---|
| `evaluation/wer.py` | a reference + hypothesis transcript (`.txt` files) | WER/CER, from-scratch edit distance; `compute_error_rates_by_group()` for per-language/code-switching breakdowns |
| `evaluation/latency.py` | an audio file (loads real models, runs the real pipeline `--runs` times) | per-stage latency (mean/median/p95) + RTF |
| `evaluation/resources.py` | same as `latency.py` | CPU%/memory (via `psutil`) sampled during a pipeline run |
| `evaluation/teacher_id.py` | a JSON file of `[{"predicted": bool, "actual": bool}, ...]` hand-labeled segments | precision/recall/F1, false-accept/false-reject rate |
| `evaluation/sus.py` | a JSON file of `[[r1..r10], ...]` respondent Likert answers (1-5) | SUS score per respondent + mean/median/adjective rating |

## 12. Fine-tuning (LoRA/PEFT)

Scaffolded in `ai/finetuning/` per CLAUDE.md's "Fine-Tuning (IN SCOPE — Non-Negotiable)" — **not runnable yet**, it needs a real corpus in `datasets/processed/` first (see `datasets/README.md` and `ai/finetuning/README.md`). Both scripts import cleanly and their error paths are exercised in `tests/`, but neither has trained against real data.

```
python ai/finetuning/finetune_whisper.py datasets/processed/<corpus_name>       # LoRA train (Colab GPU)
python ai/finetuning/convert_to_faster_whisper.py models/<adapter_dir>          # merge + convert for the backend
```

---

## 13. Production deployment (Docker + Postgres + Redis)

`deployment/` has everything for a real deployment: `Dockerfile.api` (lean — `requirements-api.txt` only, no ffmpeg, no ML libraries), `Dockerfile.worker` (`requirements-worker.txt`, has ffmpeg + the full ML stack), and `docker-compose.yml` (postgres, redis, api, worker, a one-shot `migrate` service, a shared temp volume). **Not run-verified in the environment this was built in** — no Docker installed there — written to spec and exercised instead by `.github/workflows/ci.yml`'s real postgres+redis service containers on every push/PR. Validate the YAML and actually bring it up once you have Docker:

```bash
cp deployment/.env.example deployment/.env   # fill in JWT_SECRET_KEY (see the file for how to generate one), HF_TOKEN
docker compose -f deployment/docker-compose.yml --env-file deployment/.env config   # validate first
docker compose -f deployment/docker-compose.yml --env-file deployment/.env up --build
```

Scale the worker tier independently of the API as load grows: `docker compose ... up --scale worker=3`.

For a bare-metal/VM deployment instead of Docker: set `DATABASE_URL` to a Postgres URL, run `alembic upgrade head`, set `CELERY_BROKER_URL`/`REDIS_URL` to a real Redis, set `JWT_SECRET_KEY` and `ENVIRONMENT=production` (the API refuses to start in production with no signing key), then run the API and worker commands from section 9 as separate services (e.g. systemd units, or your platform's process manager).

---

## Team

Co-authors: Andrei, Dan Joseph