# Setup — Installation, Environment, Running, Building, Rebuilding From Zero

> Written 2026-09-15. Every command below was either run directly on this machine this pass, or is
> derived directly from a config file (never invented). This machine already has everything
> installed, so the "clean machine" instructions below are reconstructed from what this machine's
> own installed versions/paths reveal, plus each tool's own standard installer — flagged
> **INFERRED** where a step wasn't literally re-run against a truly blank machine this pass.

## Clean-machine installation procedure (Windows 11, NVIDIA GPU present)

For each item: what it is, whether it's required, and how to get it.

| # | Item | Required? | How |
|---|---|---|---|
| 1 | **Python 3.11** | **REQUIRED** | This repo's `.venv` uses **3.11.9** exactly (`.venv/Scripts/python.exe --version`, confirmed this pass); CI pins `"3.11"`. Install from python.org, check "Add to PATH" during install. |
| 2 | **Flutter SDK** | REQUIRED for the client | This project was built and CI-pinned against **3.47.2** (stable channel), confirmed this pass (`flutter --version` on this machine matches exactly). Install from flutter.dev, extract somewhere permanent (this machine uses `C:\flutter`, per `android/android/local.properties`'s `flutter.sdk=C:\\flutter`), add its `bin/` to PATH. |
| 3 | **Dart SDK** | REQUIRED for the client | Bundled with the Flutter SDK above — do not install separately. This machine reports Dart **3.13.2**, matching `android/pubspec.yaml`'s `sdk: ^3.13.2` constraint. |
| 4 | **Android SDK** | REQUIRED for Android builds | Install via Android Studio, or the command-line SDK tools alone. This machine's SDK lives at `C:\Users\<user>\AppData\Local\Android\sdk` (per `android/android/local.properties`'s `sdk.dir`). Run `flutter doctor --android-licenses` after installing to accept the SDK licenses — required before any Android build will succeed. |
| 5 | **Visual Studio** | **NOT NEEDED** | This project targets Android only (`CLAUDE.md`'s explicit "iOS compatibility" out-of-scope line) — no Windows desktop Flutter target is configured, so Visual Studio's C++ workload (normally needed for Flutter Windows-desktop builds) is not required here. |
| 6 | **Git** | **REQUIRED** | This machine has **2.55.0.windows.5**. Any reasonably current Git for Windows install works. |
| 7 | **FFmpeg** | **REQUIRED** — not a Python package, must be a real executable on PATH | This machine uses the **8.1.2** "essentials" build from gyan.dev (`ffmpeg -version`, confirmed this pass), extracted with its `bin/` folder added to PATH. Both `ffmpeg` and `ffprobe` must be callable from any terminal — `backend/services/audio_service.py` shells out to `ffmpeg` directly via `subprocess.run`. |
| 8 | **CUDA Toolkit** | **NOT REQUIRED, NOT CURRENTLY USED** | Confirmed this pass: the installed `torch` build in this repo's `.venv` is `2.13.0+cpu` (`torch.version.cuda` is `None`). Installing CUDA would do nothing for this app as it currently stands — see the GPU note below if you specifically want to change that. |
| 9 | **cuDNN** | **NOT REQUIRED** | Same reasoning as CUDA above — nothing in the current dependency set needs it. |
| 10 | **NVIDIA driver** | OPTIONAL — present but unused on this machine | This machine has a working NVIDIA driver (`nvidia-smi` reports an RTX 3050, driver reporting CUDA UMD version 13.4) — but it's not required for this app to run, since nothing currently targets the GPU. |
| 11 | **Node/npm** | **NOT NEEDED** | No JavaScript/TypeScript tooling exists anywhere in this repository. |
| 12 | **Java/JDK** | REQUIRED for Android builds | This machine has **23.0.1**. `android/android/app/build.gradle.kts` targets Java 17 bytecode (`compileOptions`/`kotlin.jvmTarget`) via Gradle **9.3.1** (`gradle-wrapper.properties`) — this JDK-23-host / Java-17-target combination has produced a working debug build on this machine already (there's compiled output in `android/build/`). If you hit a Gradle/JDK compatibility error on a different machine, installing a JDK 17 LTS specifically and pointing `JAVA_HOME` at it is the standard fallback — not something this project has needed to do, but a documented common failure mode for Android/Gradle generally. |
| 13 | **Database software** | OPTIONAL | SQLite needs nothing extra (bundled with Python). PostgreSQL is only needed for the "real stack" path — install PostgreSQL 16+ natively, or skip it and use Docker/docker-compose, or skip it entirely and use the SQLite default. |
| 14 | **Redis (or Memurai on Windows)** | OPTIONAL | Only needed to run a genuinely separate Celery worker process with a real message broker. Without it, Celery's "eager mode" runs tasks inline with zero extra infrastructure — the default for local dev. Memurai is this project's own documented Windows-native Redis-compatible choice (native Redis doesn't officially support Windows). |
| 15 | **External applications** | None beyond the above | No other external app/service is required to run this project locally. |
| 16 | **Hugging Face authentication** | OPTIONAL — only for diarization | Create a free account at huggingface.co, generate an access token (Settings → Access Tokens), and accept the model terms at `huggingface.co/pyannote/speaker-diarization-community-1`. Without this, `enable_diarization` requests fail cleanly (logged, not a crash) — diarization is optional everywhere in this pipeline. |
| 17 | **API keys** | None required beyond the HF token above | Sentry (`SENTRY_DSN`) is the only other external-service credential the code reads, and it's fully optional (no-op unless set). |
| 18 | **Environment variables** | See the full table below | — |
| 19 | **Model downloads** | Automatic on first use, except the Hiligaynon fine-tune (doesn't exist) | Whisper/Silero/pyannote/SpeechBrain models are pulled from Hugging Face Hub automatically the first time the worker process loads them — no manual download step. This can take several minutes and multiple GB of disk/bandwidth on first run. |
| 20 | **System PATH modifications** | FFmpeg's `bin/`, Flutter's `bin/`, Git (usually automatic) | — |

## Environment variables — complete reference

Every variable `backend/core/config.py` reads, with nothing invented beyond what's in that file
(and `deployment/.env.example` for the two Docker-only ones).

| Variable | Meaning | Used in | Required? | Example | Secret? | Where to store |
|---|---|---|---|---|---|---|
| `JWT_SECRET_KEY` | Signs/verifies every auth token | `backend/core/security.py` | **REQUIRED** to log in at all (the app starts without it, but auth fails); **hard-required** in `ENVIRONMENT=production` (the app refuses to start) | Generate: `python -c "import secrets; print(secrets.token_hex(32))"` | **YES** | Shell env var for local dev; `deployment/.env` (gitignored) for Docker; a real secrets manager for any actual deployment |
| `DATABASE_URL` | SQLAlchemy connection string | `backend/core/config.py` | Optional — unset = SQLite file, no infra needed | `postgresql+psycopg://user:pass@127.0.0.1:5432/scaitale` | Contains a password if Postgres | Same as above |
| `HF_TOKEN` | Hugging Face access token | `backend/services/diarization_service.py` | Optional — only for `enable_diarization` | (a token string from huggingface.co) | **YES** | Same as above |
| `WHISPER_MODEL_SIZE` | Which Whisper model/path to load | `backend/services/audio_service.py` | Optional, default `"small"` | `small`, or a local fine-tuned CTranslate2 directory path | No | — |
| `WHISPER_DEVICE` | Whisper inference device | Same | Optional, default `"cpu"` | `cpu` (only value ever exercised in this project) | No | — |
| `WHISPER_COMPUTE_TYPE` | Whisper quantization | Same | Optional, default `"int8"` | `int8` | No | — |
| `WHISPER_CPU_THREADS` | CTranslate2 thread count | Same | Optional, default `0` (auto) | Physical core count, e.g. `8` | No | — |
| `TEACHER_VERIFICATION_THRESHOLD` | Cosine-similarity cutoff for "is this the teacher" | `backend/services/teacher_verification_service.py` | Optional, default `0.35` | `0.35` | No | — |
| `ENVIRONMENT` | `"development"` or `"production"` | `backend/core/config.py`, `backend/main.py` | Optional, default `"development"` | `production` | No | — |
| `CELERY_BROKER_URL` | Redis (or other) broker URL | `backend/worker/celery_app.py`, `backend/core/pubsub.py` | Optional — unset = eager mode, no broker needed | `redis://127.0.0.1:6379/0` | No | — |
| `CELERY_RESULT_BACKEND` | Celery result backend | Same | Optional, defaults to `CELERY_BROKER_URL`'s value | Same as above | No | — |
| `REDIS_URL` | Used by `pubsub.py` specifically | `backend/core/pubsub.py` | Optional, defaults to `CELERY_BROKER_URL` or `redis://127.0.0.1:6379/0` | Same as above | No | — |
| `MAX_UPLOAD_BYTES` | Upload size cap | `backend/core/rate_limit.py` | Optional, default `200MB` | `209715200` | No | — |
| `RATE_LIMIT_LOGIN` / `RATE_LIMIT_TRANSCRIBE` / `RATE_LIMIT_ENROLL` | slowapi rate strings | `backend/core/config.py` | Optional, defaults `10/minute` / `30/minute` / `10/minute` | `10/minute` | No | — |
| `SENTRY_DSN` | Error reporting endpoint | `backend/main.py` | Optional — no-op unset | (a Sentry project DSN URL) | **YES** if set | — |
| `LOG_LEVEL` | Root logger level | `backend/core/logging.py` | Optional, default `INFO` | `DEBUG` | No | — |
| `POSTGRES_PASSWORD` | Docker-compose Postgres password | `deployment/docker-compose.yml` only | Optional, defaults to `scaitale_dev_password` | (any string) | **YES** for anything beyond local dev | `deployment/.env` |

**No `.env` file currently exists in this repository** (correctly gitignored — `.gitignore` has
`.env`), and none was found on disk this pass beyond `deployment/.env.example`, which contains only
empty placeholder values, no real secrets. **To recreate one:** `cp deployment/.env.example
deployment/.env` and fill in `JWT_SECRET_KEY` (and `HF_TOKEN` if you want diarization) — this file
is for the Docker-compose path specifically; for local (non-Docker) dev, set variables directly in
your shell session instead (see the run commands below).

**Secrets currently in the repository:** **NONE FOUND.** Grepped for common secret patterns and
checked `.gitignore` coverage this pass — `.env`, `*.db`, `recordings/`, and the root-level
`/models/` are all correctly excluded from git. No hardcoded API key, token, or password was found
in any tracked file. `deployment/.env.example`'s only non-empty value is a placeholder dev password
(`scaitale_dev_password`) explicitly meant to be overridden.

## How to run the backend — copy-paste commands

**First-time setup** (from the repo root):
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
If PowerShell refuses to run the activation script: `Set-ExecutionPolicy -Scope Process
-ExecutionPolicy Bypass`, then retry.

**Fastest path — SQLite + Celery eager mode, one terminal:**
```powershell
$env:JWT_SECRET_KEY = (python -c "import secrets; print(secrets.token_hex(32))")
uvicorn backend.main:app --reload
```
Open `http://127.0.0.1:8000/docs` for interactive API docs. In eager mode, `backend/main.py`'s
`lifespan()` now preloads every ML model **at startup**, before the app accepts any traffic — so
expect the startup log itself to take longer (~35–40s: `"Eager mode detected ... preloading ML
models at startup..."` → `"ML models preloaded."` → `"Application startup complete."`), but no
individual request, including the very first WebSocket stream, should ever pay that cost or risk
a keepalive timeout. (This used to fail on the very first WS request against a cold backend —
reproduced, then fixed; see `docs/TROUBLESHOOTING.md` if you're on a version of this code from
before that fix.)

**Real stack — Postgres + Redis + a genuinely separate worker process, three terminals:**
```powershell
# Terminal 1 — API
$env:DATABASE_URL = "postgresql+psycopg://scaitale:scaitale_dev_password@127.0.0.1:5432/scaitale"
$env:CELERY_BROKER_URL = "redis://127.0.0.1:6379/0"
$env:CELERY_RESULT_BACKEND = "redis://127.0.0.1:6379/0"
$env:REDIS_URL = "redis://127.0.0.1:6379/0"
$env:JWT_SECRET_KEY = "dev-only-secret"
alembic upgrade head
uvicorn backend.main:app --reload
```
```powershell
# Terminal 2 — Worker (same env vars as Terminal 1)
celery -A backend.worker.celery_app worker --pool=solo --loglevel=info
```
**Use `127.0.0.1`, never `localhost`, for Redis specifically on Windows** — see
`docs/TROUBLESHOOTING.md`.

**GPU verification** (there is currently nothing to verify — the app never uses one; run this only
to confirm the *environment's* GPU status, not anything app-specific):
```powershell
python -c "import torch; print(torch.cuda.is_available())"
```
This prints `False` in the current `.venv` — expected, not a bug, per `CLAUDE.md` Part 1C.

**CPU fallback:** there is no separate fallback path — CPU is the only path this app currently
implements.

## How to run the Flutter app — copy-paste commands

```powershell
cd android
flutter pub get
flutter devices          # confirm an emulator or physical device is visible
flutter run               # debug mode, picks the connected device/emulator
```

**Debug vs. release:** `flutter run` (debug) vs. `flutter run --release` or `flutter build apk
--release`. **APK generation:**
```powershell
flutter build apk --release
```
Output: `android/build/app/outputs/flutter-apk/app-release.apk`. **This release build currently
signs with the auto-generated debug keystore** — `android/android/app/build.gradle.kts` has a
literal `// TODO: Add your own signing config` — fine for installing on your own devices, not a
real release key (Google Play would reject it).

**Backend URL configuration — the Android emulator localhost problem, explained precisely:**
The emulator's `10.0.2.2` is not "localhost forwarding" in the usual sense — it's a QEMU-specific
alias that routes straight back to the *host* machine's own loopback interface. That's why
`http://10.0.2.2:8000` in the Settings screen works from the emulator against a backend started
with the default `uvicorn backend.main:app --reload` (which binds to `127.0.0.1` only). **A
physical device cannot use `10.0.2.2` at all** — it needs the host machine's real LAN IP address
(`ipconfig`, look for "IPv4 Address" under the active Wi-Fi adapter), **and** the backend must be
started bound to all interfaces, not just loopback:
```powershell
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
Without `--host 0.0.0.0`, a physical phone's connection attempt is refused outright by the
loopback-only listener — silently, as a hang or connection-refused, not an error the app can
surface. You'll also need a Windows Firewall inbound rule:
```powershell
New-NetFirewallRule -DisplayName "Scaitale API" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```
And both devices must be on the same Wi-Fi network with no client/AP isolation enabled (a common
setting on school/campus/guest networks that silently blocks device-to-device traffic even on the
"same" network) — a personal hotspot from the phone itself sidesteps this if the campus network
turns out to be isolated.

## How to build the application

**Backend build/deployment:** `deployment/Dockerfile.api` and `deployment/Dockerfile.worker` exist
and are written to spec, along with `deployment/docker-compose.yml` (postgres + redis + api +
worker + a one-shot `migrate` service). **NOT CURRENTLY IMPLEMENTED / NEVER ACTUALLY BUILT** — no
Docker installation exists in any environment this project has been developed in so far. If Docker
is available:
```powershell
cp deployment/.env.example deployment/.env
# fill in JWT_SECRET_KEY, HF_TOKEN
docker compose -f deployment/docker-compose.yml --env-file deployment/.env up --build
```
Run `docker compose -f deployment/docker-compose.yml config` first to at least validate the YAML,
since this exact compose file has never been run end-to-end.

**Flutter Android build:** covered above (`flutter build apk --release`). **AAB (for Play Store
submission):** `flutter build appbundle --release` — **not something this project has ever run**;
derived from Flutter's own standard tooling, not from anything project-specific, since no
`build.gradle` customization exists for AAB output beyond Flutter's default.

**Debug vs. release, signing, assets, model files:** see the Flutter section above for signing.
No custom asset pipeline exists (`pubspec.yaml`'s `flutter: assets:` section is empty/commented
out — the app ships no bundled images/fonts beyond Flutter's own Material defaults). Model files
are never bundled into the Android app at all — they live entirely on the backend/worker side.

**Production configuration, CORS, WebSocket production config:** `backend/core/config.py`'s
`cors_allow_origins` defaults to `["*"]` with `allow_credentials=False` (deliberate — see
`docs/ARCHITECTURE.md`). **NOT CURRENTLY IMPLEMENTED:** any environment-specific CORS tightening,
a production WebSocket configuration distinct from dev (e.g. `wss://` with a real TLS cert — the
Android manifest's `usesCleartextTraffic="true"` is a deliberate local-network-only choice, not
production-ready).

## Rebuild from a completely clean machine

An exact numbered procedure, Windows 11, NVIDIA GPU present (unused), starting from nothing:

1. Install Python 3.11.x from python.org, checking "Add to PATH."
2. Install Git for Windows.
3. Download FFmpeg (gyan.dev "essentials" build or similar), extract it somewhere permanent, add
   its `bin/` folder to your system PATH. Verify: `ffmpeg -version` and `ffprobe -version` in a new
   terminal.
4. Install the Flutter SDK (3.47.2 or newer stable), extract it, add its `bin/` to PATH. Run
   `flutter doctor` and resolve anything it flags.
5. Install Android Studio (or just the command-line SDK tools), then run `flutter doctor
   --android-licenses` and accept every license prompt.
6. Install a JDK if `flutter doctor` doesn't find one already bundled with Android Studio (Android
   Studio typically ships its own).
7. Clone/copy the repository: `git clone <repo-url>` (or copy the folder if you don't have the
   remote — **MISSING PIECE**: the actual git remote URL isn't something this documentation can
   supply; use whatever source you're getting the repo from).
8. From the repo root: `python -m venv .venv`, then `.venv\Scripts\Activate.ps1`, then
   `pip install -r requirements.txt`. This installs the full ML stack and will take several
   minutes and multiple GB of disk space (PyTorch alone is large).
9. Configure the environment: at minimum, `$env:JWT_SECRET_KEY = (python -c "import secrets;
   print(secrets.token_hex(32))")`. Optionally set `HF_TOKEN` if you want diarization (see the env
   var table above for how to get one).
10. Start the backend: `uvicorn backend.main:app --reload`. The first request that touches ML
    inference will trigger model downloads from Hugging Face Hub automatically — expect this to
    take several minutes on first run, downloading multiple GB.
11. **GPU configuration:** not required for the app to run at all — skip this unless you
    specifically want to add GPU support, which this codebase does not currently implement (would
    require both a CUDA-enabled `torch` reinstall and code changes not present today).
12. In a second terminal: `cd android`, `flutter pub get`.
13. Connect an Android device via USB with Developer Options + USB debugging enabled, or start an
    Android emulator from Android Studio. Verify with `flutter devices`.
14. `flutter run` from `android/`. On first launch, open the Settings screen and set the server
    address: `10.0.2.2:8000` for an emulator, or the host machine's real LAN IP (`ipconfig`) plus
    a `--host 0.0.0.0` backend restart and a firewall rule, for a physical device (see above).
15. Perform the smoke test: see `docs/DEVELOPMENT.md` §Testing for the full manual checklist.
    Before touching Flutter at all, the fastest genuine end-to-end confidence check is the repo's
    own smoke-test scripts against the running backend from step 10 — **confirmed working this
    pass, from either location, on the first try:**
    ```powershell
    python scripts/ws_smoke_test.py     # from the repo root -- works from anywhere
    cd scripts && python v2_smoke_test.py && cd ..   # works from anywhere too, as of this fix
    ```
    Both should complete cleanly with no retry needed (the eager-mode cold-start pre-load fix in
    `backend/main.py` means the first request no longer risks a keepalive timeout). `v2_smoke_
    test.py` ends in `ALL SMOKE TESTS PASSED` on success.
    Minimum viable Flutter-side check — register an account, log in, and confirm the Home screen
    loads with an empty session list.

**Anything this procedure needs that isn't present in the repository itself:** the actual git
remote/clone source (item 7); a Hugging Face account + token, if diarization is wanted (item 9);
any real Postgres/Redis credentials, if the SQLite/eager-mode defaults aren't being used.
