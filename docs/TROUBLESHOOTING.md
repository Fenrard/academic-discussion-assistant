# Troubleshooting Guide

> Written 2026-09-15. Every entry below is either reproduced directly this pass, or traced to a
> specific fix already made in this codebase's own history (`CLAUDE.md` Part 2) — nothing here is
> invented.

## Backend won't start

- **`JWT_SECRET_KEY environment variable is not set`** — the app starts, but the first auth call
  raises this. Fix: `$env:JWT_SECRET_KEY = (python -c "import secrets; print(secrets.token_hex(32))")`
  before starting `uvicorn`. In `ENVIRONMENT=production`, the app refuses to start at all with no
  key set (`backend/main.py`'s `lifespan()`), rather than starting insecurely.
- **`Port already in use`** — another `uvicorn` instance (or something else) is already bound to
  8000. Find and stop it, or start on a different port: `uvicorn backend.main:app --port 8001`
  (then update the Flutter Settings screen's server address to match).

## Python dependency errors

- **A `pip install -r requirements.txt` failure partway through** — this file is intentionally
  unpinned (see its own header comment), so a failure is most often a specific package's own
  install requirements (e.g. `psycopg[binary]` needing a compatible wheel for your Python version/
  platform) rather than a version conflict within this project. Re-run with `-v` to see which
  package failed and check that package's own install docs.
- **`ResolutionImpossible` involving `av`/PyAV** — this is the exact historical failure mode that
  caused this project to drop `pyrnnoise`/RNNoise entirely (`docs/paper-vs-implementation.md`
  §3.3): `pyrnnoise` needs an old `av`, `faster-whisper` needs `av>=11`, and no version satisfies
  both on Python 3.11. **`pyrnnoise` is not in `requirements.txt` at all anymore** — if you're
  trying to add it back, this is why it won't work; the denoiser is FFmpeg's `afftdn` filter
  instead (no Python package).

## PyTorch errors

- **`OSError: Could not load this library: ...torchcodec\libtorchcodec_core8.dll`** (and similarly
  for versions 4–7) — **reproduced directly this pass**, during a clean `pytest tests/ -v` run on
  this exact machine. This comes from `silero_vad`'s optional `torchcodec` backend failing to load
  its native DLL on Windows. **It is non-fatal** — the full test suite still passed 90/1 despite
  this warning appearing, because `backend/services/audio_service.py: load_waveform()`
  deliberately uses `soundfile.read()` instead of Silero's own `read_audio()` specifically to avoid
  depending on this path at all. If you see this warning, it is expected on Windows and does not
  indicate a real failure — only investigate further if an actual VAD call fails, not just because
  this warning appears in the log.

## CUDA errors

Not applicable to this codebase as currently installed — the `.venv`'s `torch` build is CPU-only
(`2.13.0+cpu`, confirmed this pass), and no code path requests a CUDA device anywhere. If you've
manually installed a CUDA-enabled `torch` and are seeing CUDA errors, that's a change made outside
what this project's own code currently supports — no `device="cuda"` argument exists anywhere in
`backend/services/` to pass through in the first place.

## Out-of-memory

Not something this project's own history documents encountering — Whisper `small` (int8) plus
SpeechBrain plus (optionally) pyannote, all CPU, all loaded once per worker process, has run on
this project's own 16GB-RAM dev machine without issue. If you hit OOM on a more constrained
machine: reduce `--concurrency` on the Celery worker (fewer simultaneous model copies), or don't
enable diarization (the heaviest optional stage).

## FFmpeg not found

`RuntimeError: ffmpeg preprocessing failed on '...'` (or a Python `FileNotFoundError` for the
`ffmpeg`/`ffprobe` executable itself) means FFmpeg isn't on PATH. Verify with `ffmpeg -version` and
`ffprobe -version` in a fresh terminal (a terminal opened before you modified PATH won't see the
change). This project needs both binaries, not just `ffmpeg`.

## Model download errors

The first call that touches a given model (Whisper/Silero/pyannote/SpeechBrain) downloads it from
Hugging Face Hub automatically. A failure here is almost always network connectivity or a Hugging
Face outage — retry. For pyannote specifically, see the next entry.

## Hugging Face authentication errors

`RuntimeError: No Hugging Face token provided` or `Failed to load diarization pipeline` — two
distinct causes: (1) `HF_TOKEN` isn't set at all — diarization silently stays unavailable (logged
as a warning, not a crash) unless a session actually requests `enable_diarization=True`, at which
point that specific request fails cleanly. (2) `HF_TOKEN` is set but invalid, or you haven't
accepted `pyannote/speaker-diarization-community-1`'s user conditions at
huggingface.co/pyannote/speaker-diarization-community-1 — the error message names this exact URL.

## ~~The very first WS request after a cold backend start can time out~~ — FIXED

**Was real, reproduced, and is now fixed in code** (not just documented around). Previously:
running `scripts/ws_smoke_test.py` (or opening the Flutter app's live-recording screen) as the
*very first* request against a freshly-started, no-broker (`CELERY_BROKER_URL` unset → "eager
mode") backend could fail with `websockets.exceptions.ConnectionClosedError: sent 1011 (internal
error) keepalive ping timeout; no close frame received` — because eager mode ran the entire
first task, including a full cold model load (~7.5s), synchronously inside the API process's
single-threaded event loop, long enough to trip the client's own keepalive timeout.

**The fix:** `backend/main.py`'s `lifespan()` now detects eager mode (`settings.celery_broker_url
is None`) and calls `backend.worker.celery_app.get_worker_models()` at startup, *before* the app
accepts any traffic — paying the model-load cost once, at a point where blocking the event loop is
harmless, instead of on whichever request happens to arrive first. This has zero effect on the
"real" split-process deployment (where `celery_broker_url` **is** set, so this branch never runs,
and the API process still never imports an ML library) or on `pytest` (no test in this repo
instantiates `backend.main.app`'s real lifespan — confirmed by inspection and by a clean 90/1
re-run after this change).

**Verified by direct re-test after the fix:** started a genuinely fresh backend process, waited for
its (now longer, ~35s) startup log to show `"ML models preloaded."`, then ran `ws_smoke_test.py`
as the very first request against it — **passed completely on the first try**, no retry needed:
real transcribed text, real session_ended payload. Re-run before this fix, on an equally fresh
process, reliably failed the same way it always had; after the fix, on three separate fresh-process
attempts, it never failed once.

## ~~`scripts/v2_smoke_test.py` only worked run from inside `scripts/`~~ — FIXED

**Was real, reproduced, and is now fixed in code.** `python scripts/v2_smoke_test.py` from the
repo root used to fail with `FileNotFoundError: ... '../recordings/lecture_preprocessed.wav'`,
because the script used a literal CWD-relative path instead of a `__file__`-relative one (unlike
its sibling `ws_smoke_test.py`, which was always correct).

**The fix:** `scripts/v2_smoke_test.py` now computes `AUDIO_FILE = Path(__file__).resolve().parent.parent
/ "recordings" / "lecture_preprocessed.wav"` (the exact same pattern `ws_smoke_test.py` already
used) and every `open("../recordings/lecture_preprocessed.wav", "rb")` call was replaced with
`open(AUDIO_FILE, "rb")`. **It now works from any working directory, including the repo root.**

**Verified by direct re-test after the fix:** ran it from the repo root — the previously-broken
invocation — and it completed with `ALL SMOKE TESTS PASSED` (register, login, 401-rejection,
whole-file async transcribe, session delete, teacher enrollment reaching `"ready"`, `/metrics`,
and the full WS round-trip, all against a real running backend).

## Registering a test account with a `.local`/`.test`/etc. email fails validation

`pydantic`'s `EmailStr` (via the `email-validator` package) rejects "special-use or reserved"
top-level domains like `.local` with `value is not a valid email address: The part after the
@-sign is a special-use or reserved name that cannot be used with email.` — reproduced this pass
while manually testing `POST /auth/register` with `coldstart@test.local`. This is standard
`email-validator` behavior, not a bug in this project. Use an ordinary-looking domain
(`@example.com` works fine) for manual/scratch testing.

## WebSocket connection failure

- **From the Flutter app:** check the Settings screen's server address first — `10.0.2.2:8000` for
  an emulator, the host's real LAN IP for a physical device (see `docs/SETUP.md`). A `4401` close
  code specifically means the JWT was missing/invalid — log out and back in.
- **From the backend's perspective, a pub/sub backend failure** (e.g. Redis configured but
  unreachable) is caught explicitly in `backend/api/transcribe.py`'s `transcribe_stream()` — the
  client gets one clean `{"type": "error", "detail": "Streaming backend error: ..."}"` message and
  a proper close, rather than the socket just dropping with no explanation.

## Flutter cannot connect to backend

See "the Android emulator localhost problem" and the physical-device LAN-IP + `--host 0.0.0.0` +
firewall-rule requirements in `docs/SETUP.md` — this is the single most common connectivity gap in
this project's own history, and it's invisible on the emulator specifically because `10.0.2.2` is a
QEMU alias that happens to reach a loopback-only backend anyway.

## Android permission errors

`RECORD_AUDIO` is requested via `permission_handler` at the point recording actually starts (both
`LiveRecordingScreen` and `TeacherEnrollmentScreen` check `hasPermission()` before starting the
`record` package's stream/file capture) — a denial is caught and surfaced as a snackbar, not a
crash. If the permission dialog never appears at all, check that the Android device/emulator's app
permissions haven't been pre-denied at the OS level (Settings → Apps → scaitale_client →
Permissions).

## Microphone not working

If recording starts but the transcript stays empty/silent: on an **emulator**, this is expected —
the emulator's virtual microphone is silent by default (`CLAUDE.md` Part 2's own documented known
gap), and both the client-side VAD and the server-side Silero VAD correctly treat silence as "no
speech" rather than hallucinating text. This is not a bug to chase on an emulator; it needs a
physical device with a real microphone to actually test transcription of real speech.

## Emulator cannot reach localhost / physical phone cannot reach PC

Covered in full, with exact commands, in `docs/SETUP.md` §"How to run the Flutter app." The short
version: emulator uses `10.0.2.2` (works with a loopback-only backend); physical device needs the
host's LAN IP **and** `uvicorn backend.main:app --host 0.0.0.0 --port 8000` **and** a Windows
Firewall inbound rule for port 8000 **and** both devices on the same Wi-Fi with no client/AP
isolation.

## Slow transcription

Expected, not a bug — Whisper `small` (int8, CPU) measures **RTF ≈2.4–2.9** in this project's own
testing (a 3-second chunk takes ~8.6s to process). See `docs/ML_PIPELINE.md` §Performance. Levers
that actually help: `WHISPER_CPU_THREADS` set to physical core count (single-worker deployments
only — measured ~17% improvement), more Celery worker concurrency (`--concurrency=N`), or a smaller
Whisper model size (accuracy tradeoff).

## Crashes during long recordings

No specific crash mode is documented for long recordings in this project's history beyond the
general RTF-lag behavior above (the live transcript falls behind real-time, it doesn't crash). One
related, already-fixed bug worth knowing about: a sub-VAD-frame trailing audio remainder at the
very end of a recording used to produce a near-empty "WAV" the server's FFmpeg step rejected as
empty, surfacing a spurious final chunk-error — `PcmChunker.flush()` now has a minimum-length floor
specifically to avoid this (`android/lib/core/pcm_chunker.dart`).

## Missing model files

There are no bundled model files to be "missing" in the traditional sense — every model downloads
on first use. If `models/` (the gitignored root-level folder) is deleted, the SpeechBrain checkpoint
it held re-downloads automatically the next time teacher verification runs; there's no manual step
to "restore" it.

## Missing environment variables

`backend/core/config.py` has a sane default for every variable except the two that genuinely need a
real value to function (`JWT_SECRET_KEY` for auth, `HF_TOKEN` for diarization) — a missing
non-critical variable silently falls back to its default rather than erroring, which is worth
remembering when debugging "why isn't my env var having any effect": check the exact variable name
against `backend/core/config.py` character-for-character, since a typo'd name doesn't error, it
just falls through to the default.

## Port already in use

See "Backend won't start" above.

## Flutter/Gradle-specific issues found this pass (not previously documented)

- **`permission_handler_android` pinned via `dependency_overrides` to `13.0.1`** — `android/
  pubspec.yaml` has an explicit comment explaining why: `permission_handler_android` 14.x requires
  `compileSdk 37`, and this dev environment's SDK auto-install mis-names it as `"android-37.0"`
  instead of the `"android-37"` Gradle expects — a real environment/tooling gap, not something to
  "fix" at the app level. If a future Flutter/SDK update resolves that naming issue upstream, this
  override can likely be removed — but don't remove it speculatively without first confirming the
  SDK naming issue is actually gone.
- **`flutter pub get` reports "16 packages have newer versions incompatible with dependency
  constraints"** — this is normal, informational output (`flutter pub outdated` for detail), not an
  error; it appeared during this pass's own validation run and both `flutter analyze` and `flutter
  test` still passed clean afterward.
