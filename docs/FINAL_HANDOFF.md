# Final Handoff

> Written 2026-09-17. This is the last document in this documentation set, written on the
> assumption that no further clarification will ever be available. It is deliberately blunt.
> Nothing below is softened for morale. Every claim is either read directly from the repository/
> git history this pass, or cross-referenced to the specific companion doc that verified it
> (`docs/ARCHITECTURE.md`, `BACKEND.md`, `FRONTEND.md`, `ML_PIPELINE.md`, `SETUP.md`, `API.md`,
> `TROUBLESHOOTING.md`, `DEVELOPMENT.md`, `PROJECT_INVENTORY.md`, `CHANGE_HISTORY.md`,
> `COLD_START_VERIFICATION.md`, `ARCHITECTURE_DECISIONS.md` — all in this same `docs/` folder).

## 1. What exactly did we build?

A Flutter Android app that records classroom audio and streams it over a WebSocket to a Python
backend (FastAPI + Celery), which runs it through FFmpeg standardization, optional noise
suppression, Silero voice-activity detection, Faster-Whisper transcription (Hiligaynon/Filipino/
English, code-switched), a glossary-based text correction pass, optional pyannote speaker
diarization, and SpeechBrain ECAPA-TDNN teacher-voice verification — then generates keyword-tagged,
rule-based structured "minutes" (topics, key points, definitions, action items) from the resulting
transcript. It is a thesis prototype. It has never processed real classroom audio, never been
tested on a physical phone, and has no trained Hiligaynon-adapted model.

## 2. What is actually implemented right now?

Confirmed working by direct execution this session (not assumed): backend `pytest` suite (90
passed, 1 skipped), Flutter `flutter analyze` (clean) and `flutter test` (69 passed), a live
register→login→WS-streaming→transcription→minutes round trip via `scripts/ws_smoke_test.py` and
`scripts/v2_smoke_test.py` against a real running backend, a real `flutter build apk --debug`.
Implemented: audio capture, on-device energy-based send/skip gating, WebSocket streaming, FFmpeg
preprocessing (always on), FFmpeg `afftdn` denoise (toggle, off by default), Silero VAD (toggle, on
by default), Faster-Whisper transcription (no forced language), glossary correction, SpeechBrain
teacher verification (toggle), pyannote diarization (toggle, off by default), TextRank keyword
extraction, rule-based minutes generation, Markdown/plain-text minutes export, JWT auth, SQLite/
Postgres dual database support, the API/worker Celery split. Full status table: `CLAUDE.md` Part 3.

## 3. What did we think was implemented but is actually incomplete?

- **Hiligaynon fine-tuning.** The LoRA/PEFT scripts exist and import cleanly, but **no training
  run has ever happened**. `datasets/processed/` contains only a `.gitkeep`. No trained checkpoint
  exists anywhere, tracked or gitignored. Any claim that the deployed model is "adapted to
  Hiligaynon" is currently false — it is the stock `openai/whisper-small` weights, unmodified.
- **Diarization.** The code exists, a real bug in it was found and fixed (round 9's `.itertracks`
  unpacking fix), but **no `HF_TOKEN` has ever been configured in any environment this project has
  existed in**, meaning the actual `pyannote.audio` inference call has never once executed
  end-to-end in this project's history. The fix is inferred correct by reading pyannote's own
  serialization contract, not by observing a real successful run.
- **GPU acceleration.** The dev machine has a working RTX 3050; the installed `torch` build is
  CPU-only (`2.13.0+cpu`, confirmed by direct execution). Every performance number in this project
  is a CPU number. Nobody decided against GPU — it appears to simply never have been set up.
- **"Document export" as a Word file.** An earlier conceptual-framework draft of the thesis
  manuscript stated `python-docx` was used for export. It never was. Export is Markdown/plain text
  (`backend/api/minutes.py`). Corrected in the manuscript this session.
- **A combined SUS-plus-custom-items questionnaire.** Described as already built in some earlier
  manuscript drafts. `evaluation/sus.py` implements only the rigid, standard 10-item SUS scale —
  the "additional items" (perceived comprehension support, etc.) have no code anywhere.
- **Most of the thesis manuscript's figures.** 8 figure captions exist in Chapter 3; only **3**
  actual embedded images exist in the document (checked via `doc.inline_shapes` this session).
- **Real evaluation numbers.** WER, CER, teacher-ID precision/recall/F1, and processing time are
  all instrumented and tested — against zero real classroom audio. Every number in `CLAUDE.md`'s
  "round 8" latency section is a synthetic/lab measurement, not a thesis result.
- **Physical-device operation.** Built and verified on the Android emulator only. The
  `--host 0.0.0.0` + firewall-rule requirement for a physical phone is documented but has never
  actually been exercised.
- **Docker.** Both Dockerfiles and the compose file are written to spec. **Docker has never been
  installed in any environment this project has been developed in.** Neither image has ever been
  built, let alone run.

## 4. The 10 most important files in the entire project

1. `CLAUDE.md` — the master document. If only one file survives, it should be this one.
2. `backend/services/audio_service.py` — the pipeline orchestrator; every processing stage is
   called from `run_pipeline()` here, in a specific, structurally-required order.
3. `backend/worker/tasks.py` — where pipeline calls actually get triggered from real requests.
4. `backend/worker/celery_app.py` — model loading, eager-vs-real-broker mode switch.
5. `backend/api/transcribe.py` — the entire WebSocket streaming contract lives here.
6. `backend/core/config.py` — every environment variable and its default, in one place.
7. `backend/models/session.py` — the single denormalized table everything reads/writes.
8. `android/lib/core/pcm_chunker.dart` — client-side chunking + on-device VAD gating; the shape of
   every outgoing WebSocket frame is decided here.
9. `android/lib/core/ws_transcribe_client.dart` — the client half of the WebSocket contract; must
   stay in lockstep with `backend/api/transcribe.py`.
10. `backend/services/minutes_service.py` — the entire "structured minutes" feature in one file.

## 5. The 10 most dangerous things to change

1. **WebSocket message `type` values** (`start`/`chunk_result`/`error`/`session_started`/
   `session_ended`). A mismatch between `backend/api/transcribe.py` and `android/lib/models/
   ws_messages.dart` fails silently — an unrecognized type is simply never handled client-side.
2. **`PipelineOptions` field names** (`backend/schemas/pipeline.py` ↔ `pipeline_config.dart`'s
   `toJson()`). A renamed field on one side reverts silently to a Pydantic default — no error,
   no crash, just wrong behavior nobody notices immediately.
3. **The pipeline stage order in `run_pipeline()`.** Teacher verification structurally requires
   Whisper segments to already exist (it slices by their timestamps). Diarization's speaker-merge
   requires the same. Reordering without understanding this reintroduces the exact discrepancy
   `docs/paper-vs-implementation.md` already documents as a real, caught problem.
4. **`materialize_transcript()`'s contiguous-prefix logic.** Replacing it with simple
   arrival-order appending reintroduces the out-of-order-chunk bug this exists to prevent —
   confirmed as a real risk under a genuine multi-worker pool (round 8's 6-parallel-session test).
5. **Environment variable names in `backend/core/config.py`.** A typo'd or renamed variable falls
   back to its hardcoded default with **no error** — e.g., renaming `HF_TOKEN` silently disables
   diarization with only a log line.
6. **`SUPPORTED_EXTENSIONS`**, duplicated in `backend/services/audio_service.py` and
   `scripts/preprocess_audio.py`. Editing one without the other desyncs which files each accepts.
7. **Any `backend/models/*.py` change without a matching Alembic migration.** SQLite auto-creates
   tables; Postgres does not. The two backends silently diverge otherwise.
8. **Reverting `bcrypt`-direct auth back to `passlib`.** This is not a style preference —
   `passlib` 1.7.4 crashes outright (`AttributeError: module 'bcrypt' has no attribute
   '__about__'`) against the `bcrypt` version this project actually installs. Reproducible, not
   theoretical.
9. **Reverting Redis addressing from `127.0.0.1` to `localhost`.** Reintroduces a multi-second
   per-connection stall (or outright `TimeoutError`) on any dual-stack Windows host — measured,
   not theoretical.
10. **The model-loaded-once discipline** (`worker_process_init` / `_preload_models()` /
    `get_worker_models()`). Removing it reintroduces a ~7.5s cold-load cost on every single
    request instead of once per process — this has already caused inflated benchmark numbers
    twice, independently, in two different evaluation scripts (round 5, round 9).

## 6. The 10 most common ways this project could break

1. FFmpeg not on PATH — every audio-touching code path fails immediately (`ffmpeg`/`ffprobe` are
   shelled out to, not Python packages).
2. `JWT_SECRET_KEY` unset — auth fails; the app refuses to even start if `ENVIRONMENT=production`.
3. Redis configured with `localhost` instead of `127.0.0.1` on a Windows dual-stack host — stalls
   or outright drops WebSocket connections.
4. `requirements.txt` is **deliberately unpinned** ("intentionally unpinned while the environment
   is still in flux," its own header comment). A fresh install months from now can resolve
   different `torch`/`faster-whisper`/`pyannote` versions than this project has ever tested against.
5. A physical Android device can't reach the backend — either the backend wasn't started with
   `--host 0.0.0.0`, no firewall rule was added, or the network has client/AP isolation enabled
   (common on school/campus Wi-Fi).
6. `HF_TOKEN` missing, invalid, or the gated model's terms not accepted at huggingface.co —
   diarization fails cleanly but confusingly if a session actually requests it.
7. A database model changed without a corresponding Alembic migration — SQLite and Postgres
   silently diverge.
8. Android build toolchain mismatch on a machine other than this one — Java/Gradle/AGP version
   compatibility is unverified beyond this exact dev machine's combination (JDK 23.0.1, Gradle
   9.3.1); `permission_handler_android` is pinned to `13.0.1` specifically to work around a
   `compileSdk` naming mismatch in this dev environment's SDK auto-install.
9. A sub-`MIN_CHUNK_DURATION_SECONDS` trailing audio chunk — historically triggered a Whisper
   repetition-loop hallucination; the floor exists specifically to prevent this, and it's a
   config value someone could lower without knowing why.
10. Eager-mode's first request after a fresh backend start, if the `backend/main.py` startup
    model-preload is ever removed or bypassed — reintroduces the reproduced-this-session
    WebSocket-keepalive-timeout failure.

## 7. Commands essential to remember

```powershell
# Backend, fastest path
$env:JWT_SECRET_KEY = (python -c "import secrets; print(secrets.token_hex(32))")
uvicorn backend.main:app --reload

# Backend, physical-device-reachable
uvicorn backend.main:app --host 0.0.0.0 --port 8000
New-NetFirewallRule -DisplayName "Scaitale API" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow

# Health check
pytest tests/ -v                     # expect: 90 passed, 1 skipped
python scripts/ws_smoke_test.py      # end-to-end WS check against a running backend
cd scripts && python v2_smoke_test.py  # fuller REST+WS check; ends in "ALL SMOKE TESTS PASSED"

# Flutter
cd android
flutter pub get
flutter analyze && flutter test      # expect: clean + 69 passed
flutter build apk --debug            # produces build/app/outputs/flutter-apk/app-debug.apk

# Real (non-eager) stack
$env:DATABASE_URL = "postgresql+psycopg://scaitale:scaitale_dev_password@127.0.0.1:5432/scaitale"
$env:CELERY_BROKER_URL = "redis://127.0.0.1:6379/0"
alembic upgrade head
celery -A backend.worker.celery_app worker --pool=solo --loglevel=info
```

## 8. Fragile dependencies

- **The entire `requirements.txt` is unpinned by design.** This is the single largest source of
  future breakage risk — "works on this machine, today" is the actual current guarantee, nothing
  stronger.
- `pyrnnoise`/`audiolab` (the original denoiser) — permanently broken against `faster-whisper`'s
  `av>=11` requirement on Python 3.11; do not reintroduce.
- `torchcodec` (pulled in transitively by `torch`/`silero_vad`) fails to load its native DLL on
  this Windows machine — non-fatal (the code path that would use it is deliberately avoided via
  `soundfile` instead), but produces a large, alarming-looking warning every run.
- `permission_handler_android` pinned to `13.0.1` via a `dependency_overrides` entry specifically
  to work around a `compileSdk` naming mismatch in this dev environment's Android SDK — removing
  the pin without confirming the underlying SDK issue is fixed will likely break the Android build.

## 9. Fragile models

- **`teacher_verification_threshold` (default `0.35`)** — a literature-informed guess near a
  typical VoxCeleb equal-error-rate point, never calibrated against this project's actual target
  population or real classroom acoustics.
- **`afftdn` denoise parameters** (`nr=12:nf=-25:tn=1`) — an explicitly-labeled "unvalidated
  heuristic starting point" in the code's own comment.
- **`local_vad.dart`'s RMS threshold** (`0.01`, ~-40 dBFS) — same unvalidated-heuristic caveat,
  in the file's own doc comment.
- **Whisper's per-segment language auto-detection** — works correctly per-segment internally, but
  the session-level `language` field only ever reflects the **first** segment's result — a known,
  accepted artifact, not a bug, but easy to misread as "the system detects one language per
  session."
- **The Hiligaynon LoRA adapter does not exist.** Anything that assumes a fine-tuned model is
  loaded is wrong; the system currently runs stock `openai/whisper-small`.
- **SpeechBrain's ECAPA-TDNN model is VoxCeleb-trained, zero-shot** — never fine-tuned or validated
  against Hiligaynon/Filipino/English speakers or real classroom acoustic conditions.

## 10. Fragile configuration

- **`CELERY_BROKER_URL`'s mere presence or absence silently switches the entire task-execution
  model** (eager/inline vs. real distributed worker) — this is a one-variable, large-blast-radius
  switch with no validation or warning either way.
- **`DATABASE_URL`'s presence or absence silently switches SQLite vs. Postgres**, which have
  genuinely different concurrency/locking behavior (`FOR UPDATE` is a no-op on SQLite) — a
  correctness-relevant difference, not just a connection-string difference.
- **Any env var typo silently falls back to its hardcoded default** — `backend/core/config.py` has
  no validation layer; nothing errors on an unrecognized or misspelled variable name.
- **`WHISPER_CPU_THREADS`** — tuned for a single-worker deployment (~17% faster); actively harmful
  guidance if applied under a multi-worker pool (oversubscribes cores). Context-dependent, easy to
  misapply.

## 11. Knowledge that would normally require asking the previous Claude

This is what `docs/ARCHITECTURE_DECISIONS.md` exists to answer — read it directly rather than
re-deriving any of this. The highest-value specific examples: why `afftdn` replaced RNNoise/
`pyrnnoise` (§9, a three-stage documented history); why teacher verification runs *after*
transcription, not before (§ throughout, and `docs/paper-vs-implementation.md`); why Redis must be
addressed as `127.0.0.1` on Windows (§32); why the eager-mode backend needed a startup model-preload
fix (§27, this session's own fix); why the physical-device path needs `--host 0.0.0.0` specifically
(discovered and documented mid-session, `CLAUDE.md`'s "Known Open Issues"). For roughly a third of
the decisions catalogued in that document, the honest answer is that **no one ever wrote down why**
— see its own "Summary: decisions by rationale-completeness" table. Do not assume a plausible reason
exists just because the code looks deliberate.

## 12. What cannot be reconstructed from the source code

- Any real secret value: `JWT_SECRET_KEY`, `HF_TOKEN`, any Postgres password ever actually used.
  None are in the repository (confirmed via a targeted secrets scan this session), and none can be
  recovered from it.
- The **original** reasoning behind foundational choices marked `RATIONALE UNKNOWN` in
  `docs/ARCHITECTURE_DECISIONS.md`: why FastAPI, why WebSocket from day one, why Silero VAD, why
  SpeechBrain's ECAPA-TDNN, why `slowapi`, why Flutter's `provider` package. These predate any
  recorded reasoning in this project's own history.
- Any real classroom audio, or the human judgment that would come from listening to it — none
  exists anywhere in this repository or its history.
- The thesis committee's actual expectations, feedback, or grading criteria — not in this repo, not
  derivable from it.
- Nathan's own current priorities/timeline beyond what's written in `CLAUDE.md`'s "Working
  Dynamic" and "Data Collection Tracking" sections, which are themselves a point-in-time snapshot.

## 13. Previous implementation attempts that should NOT be repeated

- **`pyrnnoise`/RNNoise for denoising.** Permanently broken against this project's other pinned
  dependencies on Python 3.11 (`ResolutionImpossible` against `faster-whisper`'s `av` requirement).
  Do not reintroduce without first solving that dependency conflict, which nothing in this
  project's history has managed to do.
- **`passlib`'s `CryptContext` for password hashing.** Crashes outright against the `bcrypt`
  version this project installs. Use `bcrypt` directly, as currently implemented.
- **`celery_app.send_task("name", ...)` instead of `.delay()` on an imported task object.** Silently
  ignores `task_always_eager` — breaks the entire eager-mode dev/test/CI path without any error.
- **Naive diarization output unpacking** (`for turn, speaker in output.speaker_diarization`).
  Breaks with `AttributeError` on `pyannote/speaker-diarization-community-1`'s actual return shape.
  Use `.itertracks(yield_label=True)`, as currently implemented.
- **Loading Silero (or any model) fresh inside a benchmarking/evaluation loop instead of once.**
  Happened independently in two different evaluation scripts (`latency.py`, then `resources.py`)
  and inflated the exact numbers each script exists to measure both times.
- **Making FFmpeg preprocessing conditional/skippable anywhere.** Caused a real, reproduced
  "Expected 16000Hz, got Xhz" crash in teacher enrollment when this rule was accidentally skipped.

## 14. Technical debt

- `materialize_transcript()`/`append_chunk_result()` are O(n²) across a session's total chunk
  count — acceptable at this project's tested scale, a real problem at lecture length (hundreds to
  ~1200 chunks/hour), never fixed, only documented.
- SpeechBrain teacher verification runs once per Whisper segment with no batching — 40-60+
  sequential CPU forward passes for a typical session.
- `evaluation/wer.py`'s edit-distance uses a full O(n·m) matrix, not a rolling buffer, even for
  whole-session character-level CER.
- `write_report()` is copy-pasted near-identically across all five `evaluation/*.py` scripts.
- `_get_session_or_404` (in `minutes.py`) isn't shared with the equivalent inline checks in
  `sessions.py`/`teacher.py`.
- `LICENSE` at the repo root is an empty directory, not a file — a direct, acknowledged violation
  of this project's own documented rule that it must be a root-level file. Left unresolved because
  the actual license choice is Nathan's decision, not something to invent.
- All Flutter↔backend traffic is plaintext HTTP/WS (`usesCleartextTraffic="true"`) — accepted for a
  trusted local classroom Wi-Fi, a real gap the moment this ever serves anything less trusted.
- Docker images are entirely unbuilt and unverified as containers, in every environment this
  project has ever existed in.

## 15. What a new developer should understand before touching the code

The system is two separate OS processes, not one — an API tier that never runs ML code, and a
worker tier that does everything else — and this split exists specifically because an earlier,
simpler version blocked its own event loop on every transcription (a measured bug, not a
hypothetical). The pipeline's stage order is not arbitrary: teacher verification and diarization's
speaker-merge both structurally require Whisper's segments to already exist. This is a **thesis
prototype**: nearly every numeric threshold in the system (denoise parameters, VAD thresholds, the
teacher-verification cosine cutoff) is an explicitly-labeled unvalidated default, not a tuned
production value. The language scope (Hiligaynon/Filipino/English only) is a strictly enforced
rule, not a soft preference — a fourth language reference anywhere is treated as an error. The
thesis manuscript and the code have known, tracked points of disagreement
(`docs/paper-vs-implementation.md`) — never assume the manuscript's prose is what the code
actually does without checking.

## 16. What should be tested before every major change

`pytest tests/ -v` (expect 90 passed, 1 skipped) and `flutter analyze && flutter test` (expect
clean + 69 passed) at minimum, every time. If the change touches `backend/services/audio_service.py`
or its call order: run both smoke-test scripts against a live backend afterward — unit tests do not
exercise the full real-model pipeline end to end the way `scripts/ws_smoke_test.py`/
`v2_smoke_test.py` do. If the change touches any `backend/models/*.py`: verify both the SQLite
auto-create path and, if possible, a real Postgres + `alembic upgrade head` path — they are not
guaranteed to agree. If the change touches anything in the WebSocket contract or `PipelineOptions`:
verify both sides (`backend/api/transcribe.py`/`backend/schemas/pipeline.py` and their Dart
counterparts) were updated together — a mismatch here produces no error, just silently wrong
behavior.

## 17. If the project stops working tomorrow, check FIRST

1. Is FFmpeg actually on PATH in this shell (`ffmpeg -version`, `ffprobe -version`)?
2. Is `JWT_SECRET_KEY` set in this shell session?
3. Does `pytest tests/ -v` pass at all, in isolation, before touching the rest of the stack?
4. Does `uvicorn backend.main:app --reload` start cleanly and does `GET /health` respond?
5. If a real Redis/Postgres is configured: are the URLs using `127.0.0.1`, not `localhost`?
6. Did a `pip install -r requirements.txt` on a different machine or after time has passed
   silently resolve different (untested) versions of `torch`/`faster-whisper`/`pyannote`/
   `speechbrain`? This file is unpinned by design — check this before assuming the code changed.
7. Does the Flutter app's Settings screen server address actually match how the backend was
   started (`10.0.2.2` for an emulator, a real LAN IP + `--host 0.0.0.0` for a physical device)?

## 18. If you have only 30 minutes to recover the project

```powershell
cd academic-discussion-assistant
python -m venv .venv                                 # only if .venv is missing/corrupted
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:JWT_SECRET_KEY = (python -c "import secrets; print(secrets.token_hex(32))")
pytest tests/ -v                                       # expect 90 passed, 1 skipped
uvicorn backend.main:app --reload                      # then, separately: curl http://127.0.0.1:8000/health
```
That confirms the backend is alive. For the client, in a second terminal: `cd android`,
`flutter pub get`, `flutter analyze && flutter test`. If both halves pass, the project is in the
same state this handoff document describes it in — nothing has silently regressed since this pass.

## 19. If you have one day to understand the project, read this order

1. `CLAUDE.md` Part 1, in full.
2. `docs/ARCHITECTURE.md` — the real traced data flow, every workflow, the contracts table.
3. `docs/ML_PIPELINE.md` — every model, what it does, its actual measured performance.
4. `backend/services/audio_service.py` and `backend/worker/tasks.py`, read directly, not summarized.
5. `android/lib/screens/recording/live_recording_screen.dart`, read directly.
6. `docs/ARCHITECTURE_DECISIONS.md`, skimmed — enough to know which design choices have a reason
   on record and which don't, so you don't waste time hunting for a rationale that was never
   written down.

## 20. If you have one week to continue development, understand this first

Everything in "one day" above, plus: `docs/DEVELOPMENT.md` in full (the known-bugs list and the
Safe Modification Guide table — it tells you exactly which file to touch for a given kind of
change, and what not to touch alongside it); `CLAUDE.md` Part 2 in full — every one of the eleven
documented bug-hunt "rounds" describes a mistake that was already made and fixed once; repeating
one wastes a week re-discovering it. Run both smoke-test scripts against a live backend yourself at
least once, don't just trust that they still pass. Read `docs/paper-vs-implementation.md` before
touching anything that the thesis manuscript also describes, since a code change there may create a
new manuscript-vs-code disagreement that this project's own convention requires tracking. Finally:
understand that almost every "what's left" item (`CLAUDE.md` Part 3, "What should be worked on
next") is blocked on the same single dependency — real classroom audio does not exist yet anywhere
in this project. Fine-tuning, real evaluation numbers, and threshold calibration cannot proceed
without it. Building more pipeline features without that audio existing does not move the thesis's
actual open objectives forward.
