# Setup Automation

> Written 2026-09-19. Answers two questions: **can this project's setup actually be automated
> safely**, and **exactly what do `scripts/check_environment.ps1`, `scripts/setup_backend.ps1`,
> and `scripts/setup_frontend.ps1` each do** (and, just as importantly, refuse to do). Every
> script here was written this pass, parse-checked, and `check_environment.ps1` (the read-only
> one) was actually run against this dev machine to confirm its output — see the worked example
> below. `setup_backend.ps1` was also run for real against this machine's existing `.venv`.

## Can this project be made reproducible with setup scripts? (Analysis)

**Partially, and that partial split is the actually useful answer — not "yes" or "no."**

This repository already keeps two categories of setup cleanly separated, and the honest answer
tracks that split exactly:

**Safe to automate (project-level, deterministic, already declared in the repo):**
- Creating a Python virtual environment and installing *this repo's own* pinned/declared
  dependencies (`requirements.txt` / `requirements-api.txt` / `requirements-worker.txt`) into it.
- Fetching Flutter's pub dependencies (`android/pubspec.yaml` already declares exactly what's
  needed — `flutter pub get` adds nothing not already specified).
- Scaffolding a `.env` from `.env.example` (never overwriting a real one) and generating a
  throwaway dev-only `JWT_SECRET_KEY` the *first* time that file is created — a value any dev
  install needs before anything auth-gated will work at all, and one this project's own docs
  already say "any value works for local dev."
- Creating the handful of empty, gitignored runtime directories (`recordings/`, `transcripts/`,
  `models/`) the app already auto-creates some of at import time anyway
  (`backend/core/config.py`'s `settings.transcripts_dir.mkdir(...)`) — pure convenience,
  idempotent, never destructive.
- Checking (never installing) that system-level prerequisites are present: Python, FFmpeg/
  ffprobe, Git, Flutter/Dart, and reporting GPU/Postgres/Redis presence for information only.

**Not safe to automate, and this pass deliberately does not attempt it:**
- **Installing Python, FFmpeg, Flutter, the Android SDK, a JDK, Postgres, or Redis/Memurai
  themselves.** These are real, opinionated, version-sensitive system installs — silently
  fetching and running an installer for any of these on a machine that might already have a
  different version, a different install location, or a reason not to want one, is exactly the
  "blindly install arbitrary software" behavior this task explicitly rules out. Every one of
  these is a manual step in `docs/SETUP.md`, and stays that way.
- **CUDA-enabled `torch`.** Per `docs/MODIFICATION_COOKBOOK.md` entry 24, this needs a
  driver/CUDA-version-matched wheel choice a script can't safely infer, plus this project
  currently has *zero* GPU-aware code for two of its four models (SpeechBrain, pyannote) — even
  a perfect CUDA install wouldn't finish the job. Genuinely a manual, code-plus-environment change,
  not a setup-script task.
- **`android/android/local.properties`.** This records a machine-specific Android SDK path.
  Guessing it wrong points the whole Gradle build at a path that doesn't exist. Flutter/Android
  Studio already generate this correctly the first time you open or run the project — that's the
  right tool for this job, not a setup script.
- **A real Postgres database or Redis/Memurai broker.** Entirely optional for this project (SQLite
  + Celery's eager mode is the documented zero-infra default — see `CLAUDE.md`'s "Development
  Environment" section) — automating an install that most contributors don't even need, and that
  has real security/service-account implications when it *is* wanted, isn't in scope here.
- **`HF_TOKEN`.** Requires a human to create a Hugging Face account and accept
  `pyannote/speaker-diarization-community-1`'s model terms — there's no way to automate consent.

**The upshot:** the *project-level* parts of this repo's setup (venv, pip deps, pub deps, a
starter `.env`, runtime directories) are fully reproducible and now scripted. The *system-level*
parts (language runtimes, FFmpeg, optional infra, a Hugging Face account) remain — correctly —
manual, one-time, per-machine steps that a script has no safe way to make automatic. This mirrors
`docs/ML_REPRODUCIBILITY.md`'s own finding for model weights: everything that *can* download
itself deterministically already does (Whisper/SpeechBrain via Hugging Face Hub, Silero bundled in
its pip package); only pyannote's *gated* download needs a human's one-time consent, for the same
reason `HF_TOKEN` can't be scripted here.

## The scripts

### `scripts/check_environment.ps1` — read-only diagnostic

**What it does.** Runs a battery of presence/version checks and prints a categorized PASS / WARN /
INFO / FAIL report: repo-root sanity, Git, Python (and whether it's 3.11.x, this project's
known-good version), the `.venv` (and, if present, whether `torch` inside it is CPU or CUDA-
enabled — informational, matches `docs/MODIFICATION_COOKBOOK.md` entry 24's GPU note), FFmpeg/
ffprobe, Flutter/Dart, `android/android/local.properties`, `.env` and whether `JWT_SECRET_KEY` is
set *somewhere* (in `.env` or as a real environment variable — never prints the actual value),
optional `HF_TOKEN`/`DATABASE_URL`/`CELERY_BROKER_URL`/`SENTRY_DSN` presence (also value-masked),
Postgres (`psql` presence only), Redis/Memurai (a single read-only TCP probe against
`127.0.0.1:6379`, nothing sent or read), and GPU/`nvidia-smi` presence.

**What it changes.** Nothing. Every check is `Get-Command`, `Test-Path`, a `--version`/`-V`
invocation, or one `Test-NetConnection` probe. No file is created, deleted, or modified; no
service is started or stopped; no package is installed.

**Worked example** (run for real against this dev machine, this pass):

```
Repo       [PASS] Running from the repo root.
Git        [PASS] git version 2.55.0.windows.5
Python     [PASS] Python 3.11.9 (matches this project's known-good version, per CLAUDE.md).
Virtualenv [PASS] .venv exists (Python 3.11.9).
Virtualenv [INFO] torch 2.13.0+cpu | CUDA available: False
FFmpeg     [PASS] ffmpeg version 8.1.2-essentials_build-www.gyan.dev ...
FFmpeg     [PASS] ffprobe also on PATH.
Flutter    [PASS] Flutter 3.47.2 - channel stable - https://github.com/flutter/flutter.git
Flutter    [INFO] dart: Dart SDK version: 3.13.2 (stable) ...
Flutter    [PASS] android\android\local.properties exists.
Config     [WARN] .env not found.
Postgres   [INFO] psql not found on PATH - fine if you're using the SQLite default.
Redis      [INFO] Something is listening on 127.0.0.1:6379 (likely Redis/Memurai).
GPU        [INFO] nvidia-smi found - an NVIDIA GPU/driver is present ...
```

Every line above was produced by actually running the script, not written by hand — it correctly
found this machine's real FFmpeg 8.1.2, Flutter 3.47.2, and CPU-only torch build, matching
`CLAUDE.md`'s independently-verified Tech Stack table exactly.

**A real bug this pass caught and fixed while writing this script**: `ffmpeg --version`/
`ffprobe --version` write their banner to **stderr**, not stdout. Under
`$ErrorActionPreference = 'Stop'` (this script's own top-of-file setting, deliberately strict so a
genuine script bug doesn't fail silently), PowerShell 5.1 turns even a *successful* native
command's stderr text into a terminating error the moment it's touched by output redirection —
confirmed directly against this exact FFmpeg build, and true even for `2>$null`, not just the
`2>&1` case this tool's own PowerShell guidance already warns about. Fixed by locally relaxing
`$ErrorActionPreference` to `'Continue'` around just that one native-command invocation (in
`Get-CommandVersion`), then restoring it — not by changing the redirection, which turned out not
to be the actual fix.

### `scripts/setup_backend.ps1` — backend project-level setup

**What it does, in order:**
1. Runs `check_environment.ps1` first, so you see the diagnostic before anything changes.
2. Creates `.venv` **only if it doesn't already exist** (`python -m venv .venv`). An existing
   `.venv` is left completely alone — not recreated, not upgraded in place beyond the pip install
   in step 3.
3. `pip install --upgrade pip`, then `pip install -r <requirements file>` (default
   `requirements.txt`, the full local-dev union; pass `-Requirements requirements-worker.txt` or
   `-Requirements requirements-api.txt` for a leaner install matching one tier only) — an ordinary
   incremental `pip install`, safe to re-run any number of times.
4. Copies `.env.example` to `.env` **only if `.env` doesn't already exist**, generating a fresh
   random `JWT_SECRET_KEY` into that new copy only (via
   `python -c "import secrets; print(secrets.token_hex(32))"`, the exact command `CLAUDE.md`
   already documents by hand). Every other value in the generated `.env` is left as the safe
   blank/default placeholder from `.env.example` — nothing else is guessed or filled in.
5. Creates `recordings/`, `transcripts/`, `models/` with `New-Item -ItemType Directory -Force` —
   a genuinely idempotent operation on an existing populated directory (it does not clear or
   recreate one that already has real files in it, such as this project's own
   `models/speechbrain_spkrec-ecapa-voxceleb/`).
6. By default, runs `pytest tests/ -v` as a real verification step (pass `-SkipTests` to skip) —
   expect `90 passed, 1 skipped` against the SQLite default.

**What it never does:** install Python, FFmpeg, Postgres, or Redis; touch an existing `.venv`'s
packages beyond an ordinary `pip install`; overwrite an existing `.env`; delete anything.

**Verified this pass**: run for real against this machine's existing `.venv` (already fully
provisioned per `CLAUDE.md`'s own `pip freeze` record) — correctly detected and reused the
existing `.venv` without touching it, ran a no-op-equivalent `pip install` against
already-satisfied dependencies, and (since `.env` didn't exist yet on this machine before this
pass) created a real `.env` with a freshly generated `JWT_SECRET_KEY`.

### `scripts/setup_frontend.ps1` — Flutter project-level setup

**What it does, in order:**
1. Verifies `flutter` is on PATH — **hard-fails with install guidance if not** (there is no safe
   fallback; this script cannot proceed without a real Flutter SDK, and will not install one).
2. Runs `flutter pub get` inside `android/` — fetches exactly what `android/pubspec.yaml` already
   declares; nothing is added to that file.
3. Reports whether `android/android/local.properties` exists — **never creates one** (see the
   Analysis section above for why guessing this is unsafe).
4. Reports connected devices/emulators via `flutter devices` — informational only; starts nothing.
5. With `-RunChecks`, also runs `flutter analyze` and `flutter test` (both read-only) as a real
   verification step — expect a clean analyze and `12` passing test files (this project's Flutter
   suite as of this pass, per `docs/MODIFICATION_COOKBOOK.md`'s file-by-file test inventory).

**What it never does:** install Flutter, the Android SDK, or a JDK; create/guess
`local.properties`; modify `pubspec.yaml`; start an emulator; touch `android/android/` (the native
Gradle project) or delete `android/build/`.

## Environment variables — `.env.example`

`.env.example` (repo root, new this pass) lists every environment variable
`backend/core/config.py`'s `Settings` class and `backend/core/security.py` actually read, each
with a comment explaining what it's for, whether it's required, and — for anything with a safe
non-secret default — that default pre-filled (`WHISPER_MODEL_SIZE=small`,
`WHISPER_DEVICE=cpu`, `ENVIRONMENT=development`, the documented rate-limit strings, etc.). Real
secrets (`JWT_SECRET_KEY`, `HF_TOKEN`, `DATABASE_URL`, `SENTRY_DSN`) are left blank in the
template — `setup_backend.ps1` fills in only `JWT_SECRET_KEY`, and only with a freshly generated
dev-only value, only on a brand-new `.env`.

One thing worth knowing: **this project has no `python-dotenv` dependency** — nothing in
`backend/` automatically loads a `.env` file at startup. `.env` (and `.env.example`) exist purely
as a convenience reference and as the source `setup_backend.ps1` copies from; you still need to
actually export these as real process environment variables before starting the server (e.g.
`Get-Content .env | ForEach-Object { if ($_ -match '^([^#=]+)=(.*)$') { Set-Item "env:$($Matches[1])" $Matches[2] } }`,
or set them one at a time as `CLAUDE.md`'s own quick-start already shows for `JWT_SECRET_KEY`).
This is a deliberate, pre-existing project choice (see `docs/ARCHITECTURE_DECISIONS.md` if it logs
a rationale) — this pass did not add dotenv loading, only the template file.

## What still must be installed/configured manually, full list

| Item | Why it's manual | Where it's documented |
|---|---|---|
| Python 3.11 itself | System-level runtime install | `docs/SETUP.md` |
| FFmpeg + ffprobe on PATH | System-level binary, not a pip package | `docs/SETUP.md` |
| Flutter SDK + Dart (bundled) | System-level SDK install | `docs/SETUP.md` |
| Android SDK + a JDK | System-level, version-sensitive | `docs/SETUP.md` |
| `android/android/local.properties` | Machine-specific path; auto-generated correctly by Android Studio/Flutter tooling | `scripts/setup_frontend.ps1`'s own output |
| `JWT_SECRET_KEY` for anything beyond local dev | A real secret; the setup script's auto-generated dev value is explicitly dev-only | `.env.example`, `docs/SETUP.md` |
| `HF_TOKEN` (optional) | Requires a Hugging Face account + accepting gated-model terms, a human consent step | `docs/ML_REPRODUCIBILITY.md` |
| PostgreSQL (optional) | Real infra with its own service/credentials; SQLite is the default | `docs/SETUP.md` |
| Redis / Memurai (optional) | Real infra; Celery's eager mode needs neither | `docs/SETUP.md` |
| CUDA-enabled `torch` + GPU code changes (optional) | Driver-version-specific wheel choice, plus missing GPU code paths in two of four models | `docs/MODIFICATION_COOKBOOK.md` entry 24 |
| A real Docker install (optional) | Never installed in any environment this project has been developed in so far | `CLAUDE.md`'s Status Report |

## Quick start with these scripts

```powershell
# From the repo root:
.\scripts\check_environment.ps1        # read-only — see what's missing before anything changes
.\scripts\setup_backend.ps1            # venv, pip deps, .env, runtime dirs, pytest verification
.\scripts\setup_frontend.ps1 -RunChecks # flutter pub get, plus analyze+test verification

# Then, same as CLAUDE.md's own quick-start:
uvicorn backend.main:app --reload
# --- separate terminal ---
cd android
flutter run
```
