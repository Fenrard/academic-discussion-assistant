# Dependency Reproducibility Audit

> Written 2026-09-19, from a full inspection of every dependency-declaring file in this
> repository (`requirements*.txt`, `android/pubspec.yaml` + `android/pubspec.lock`,
> `deployment/Dockerfile.api`/`Dockerfile.worker`/`docker-compose.yml`, `.github/workflows/ci.yml`,
> `scripts/`, `alembic.ini`) plus a live inspection of this machine's actual `.venv`
> (`pip freeze`, direct `import torch; torch.__version__`/`torch.cuda.is_available()`) and Android
> toolchain (`gradle-wrapper.properties`, `settings.gradle.kts`, installed SDK platforms,
> `java -version`). **No dependency was upgraded, downgraded, or otherwise changed to produce this
> document** — every version below is either what's currently declared in a repo file, or what's
> currently, actually installed on this dev machine, clearly labeled which.
>
> **Read this alongside `docs/ML_REPRODUCIBILITY.md`** (per-model source/weights/license detail —
> this file covers the *package* layer, that one covers the *model-weight* layer) and
> `docs/SETUP_AUTOMATION.md` (how to actually (re)create a working environment from these
> declarations).

## Executive summary — is this reproducible today?

**Partially, by design in one place and by accident in two others:**

- **Flutter/Dart side: yes, fully reproducible.** `android/pubspec.lock` exists, is checked into
  git (not gitignored), and pins all 100 resolved packages (direct + transitive) to exact
  versions. `flutter pub get` against this lockfile reproduces the exact same dependency tree on
  any machine. **This is the one part of this repo that needs no changes to be considered properly
  locked.**
- **Python side: deliberately unpinned, by the project's own stated choice** —
  `requirements.txt`'s own header comment says: *"Intentionally unpinned while the environment is
  still in flux."* This is a real, working tradeoff during active development, not an oversight —
  but it does mean a fresh `pip install -r requirements.txt` today can silently resolve to
  different (newer) versions than what's actually running on this dev machine, especially for
  fast-moving packages like `transformers`/`huggingface_hub`/`torch`. See "What should be pinned"
  below for the specific, minimal fix that preserves today's exact working set without freezing
  the whole file forever.
- **A real, unintentional drift exists between `requirements.txt` and this dev machine's actual
  `.venv`**: five packages are installed and importable right now that are **not declared in any
  requirements file at all** — `pyrnnoise`, `audiolab`, `passlib`, `python-docx`, `python-dotenv`.
  None of these are dangerous (all are confirmed-unused leftovers or one-off tool installs — see
  the per-package notes below), but a clean `pip install -r requirements.txt` on a fresh machine
  will **not** have them, which is correct (they shouldn't be there), but is worth knowing before
  anyone is surprised a fresh install "is missing" something this dev `.venv` happens to have.
- **Docker/CI images float on minor versions, not exact ones**: `python:3.11-slim` (both
  Dockerfiles), `postgres:16-alpine`, `redis:7-alpine` (compose + CI), and CI's
  `actions/setup-python@v5` with `python-version: "3.11"` all resolve to whatever the latest patch
  of that minor version is *at build time* — reproducible in spirit (same minor line) but not
  byte-for-byte reproducible build-to-build. `apt-get install ffmpeg` inside `Dockerfile.worker`
  is fully unpinned — it gets whatever FFmpeg version is in Debian's repo at build time, which is
  **not guaranteed to be anywhere near this dev machine's FFmpeg 8.1.2** (a materially different,
  much older FFmpeg typically ships in Debian stable's repos — this is a genuine version-skew risk
  between "what was tested on this dev machine" and "what the Docker image would actually run").

## Python / backend

### Python interpreter

| | Value | Source |
|---|---|---|
| Exact version, this dev machine | **3.11.9** | `python --version`, run live this pass |
| Declared minimum | 3.11 (implied — CI pins `"3.11"`, Docker uses `python:3.11-slim`) | `.github/workflows/ci.yml`, both Dockerfiles |
| Declared maximum | **None declared anywhere** | No `python_requires` exists — there is no `pyproject.toml`/`setup.py`/`setup.cfg` in this repo at all; nothing pins an upper bound |
| Why 3.11 specifically | `faster-whisper`/`torch` ecosystem compatibility at time of writing (per `CLAUDE.md`'s Tech Stack table) | `CLAUDE.md` |

**No `pyproject.toml` exists in this repository.** All Python dependency declaration is via the
three flat `requirements*.txt` files (pip's plain format, no `pip-tools`/`poetry`/`pdm` lockfile
layer on top). This means there is currently no single place that pins a Python version range for
tooling (pip, linters, IDEs) to read — see "What should be pinned" below.

### Requirements files — what's declared, and how loosely

| File | Purpose | Pinning style |
|---|---|---|
| `requirements.txt` | Full local-dev/CI union of the two below | **Unpinned** — bare package names, no version specifiers at all (e.g. `fastapi`, `torch`, `faster-whisper`) |
| `requirements-api.txt` | Lean API-tier subset (no ML) | **Unpinned**, same style |
| `requirements-worker.txt` | Full ML subset (worker tier) | **Unpinned**, same style |

Every one of the ~30 declared packages across these three files is a bare name with no `==`, `>=`,
or `<` specifier anywhere. This is a real, stated project decision (see the Executive Summary),
not something this pass changed or is recommending be reversed wholesale.

### Exact installed versions — this dev machine's `.venv`, right now

The full `pip freeze` output below is **machine-and-moment-specific evidence**, not a
specification — it is what's *actually* installed and running on this dev machine as of this
pass, captured directly (`'.venv/Scripts/python.exe' -m pip freeze`), not carried forward from an
older doc. Grouped by relevance:

**Core backend framework:**
```
fastapi==0.141.1          uvicorn==0.52.4           websockets==17.1
starlette==1.6.0          SQLAlchemy==2.0.51        alembic==1.18.5
psycopg==3.3.4            psycopg-binary==3.3.4     PyJWT==2.13.0
bcrypt==5.0.0             email-validator==2.3.0    python-multipart==0.0.32
celery==5.6.3             redis==8.1.0              slowapi==0.1.10
prometheus-fastapi-instrumentator==8.1.0             sentry-sdk==2.68.1
networkx==3.6.1           pydantic==2.13.5           pydantic_core==2.46.5
```

**ML / audio pipeline (worker tier):**
```
torch==2.13.0+cpu         torchaudio==2.11.0+cpu    torchcodec==0.15.0
faster-whisper==1.2.1     ctranslate2==4.8.1        silero-vad==6.2.1
pyannote-audio==4.0.7     pyannote-core==6.0.1      pyannote-database==6.1.1
pyannote-pipeline==4.0.0  pyannote-metrics==4.1     pyannoteai-sdk==0.4.0
speechbrain==1.1.1        lightning==2.6.5          pytorch-lightning==2.6.5
torch-audiomentations==0.12.0   pytorch-metric-learning==2.9.0
asteroid-filterbanks==0.4.0     torch_pitch_shift==1.2.5
soundfile==0.14.0         sounddevice==0.5.5        av==18.0.0
onnxruntime==1.27.0       sentencepiece==0.2.2      numpy==2.4.6
scipy==1.17.1             optuna==4.9.0             huggingface_hub==1.23.0
tokenizers==0.23.1        safetensors==0.8.0
```

**Fine-tuning tooling (`ai/finetuning/`, not needed to run the app):**
```
transformers==5.16.1      peft==0.20.0              accelerate==1.14.0
datasets==5.0.1           pyarrow==25.0.1
```

**Evaluation scripts (`evaluation/`, not needed to run the app):**
```
pandas==3.0.3             matplotlib==3.11.1        psutil==7.2.2
scikit-learn==1.9.0
```

**Dev/test only:**
```
pytest==9.1.1
```

**Installed but NOT declared in any requirements file (drift — see below for what each is):**
```
pyrnnoise==0.4.3          audiolab==0.5.2           passlib==1.7.4
python-docx==1.2.0        python-dotenv==1.2.3
```

Full raw `pip freeze` (all ~150 packages including transitive dependencies) is not reproduced
here in full to keep this document navigable — the packages above are every one with a direct
`import` somewhere in `backend/`, `scripts/`, `ai/`, or `evaluation/`; everything else is a
transitive dependency pulled in by one of them.

### The five undeclared packages — what each one is and why it's there

- **`pyrnnoise==0.4.3`, `audiolab==0.5.2`** — the original denoiser dependency, confirmed dropped
  from every requirements file in commit `1f23a71` (see `docs/GIT_HISTORY.md`) after `pyrnnoise`
  0.4.3 proved permanently broken against every installable `audiolab`/PyAV combination on Python
  3.11. Still physically present in this `.venv` because uninstalling a package that's no longer
  declared is never automatic in pip's model — nothing in `backend/`, `scripts/`, or anywhere else
  imports either package anymore (confirmed: `docs/CODEBASE_DEPENDENCY_MAP.md`'s import graph has
  zero references). **Safe, inert leftovers** — not a functional risk, but also proof that this
  `.venv` is not identical to what `pip install -r requirements.txt` alone would produce today.
- **`passlib==1.7.4`** — never used by this project's actual auth code (`backend/core/
  security.py` uses `bcrypt` directly specifically *because* passlib's `CryptContext` breaks
  against modern bcrypt — see that module's own docstring). Likely an early-development leftover
  from before that decision was made. Confirmed zero imports anywhere in `backend/`.
- **`python-docx==1.2.0`** — installed as a one-off tool this session, to programmatically edit
  the actual thesis `.docx` manuscript (Chapters 1 and 3) per an explicit user request earlier in
  this project's history — not an application dependency. `CLAUDE.md`'s Tech Stack table already
  states "python-docx — NOT USED ANYWHERE" referring to the *application* (minutes export is
  Markdown/plain-text, not `.docx` — see `backend/api/minutes.py`); that claim is still accurate
  for `backend/`. Confirmed zero imports anywhere in `backend/`, `scripts/`, `ai/`, or
  `evaluation/`.
- **`python-dotenv==1.2.3`** — not imported anywhere in this codebase either (confirmed via
  grep). `docs/SETUP_AUTOMATION.md` (written this session) already notes this project has no
  dotenv-loading dependency and `.env` files are a manual/convenience artifact only, not
  auto-loaded — this installed package is consistent with that note (present but genuinely
  unused), not a contradiction of it.

**None of these five need to be added to any requirements file** — they are correctly *absent*
from the declarations; the drift is real but harmless. Listed here purely so a future audit (or a
"why does `pip freeze` show X" question) isn't a mystery.

### PyTorch / CUDA compatibility

| | Value |
|---|---|
| Installed build | `torch==2.13.0+cpu` (confirmed via direct `python -c "import torch; print(torch.__version__)"` this pass) |
| `torch.version.cuda` | `None` |
| `torch.cuda.is_available()` | `False` |
| `torchaudio` | `2.11.0+cpu` (matching CPU-only build) |
| `ctranslate2` (faster-whisper's inference runtime) | `4.8.1` — also CPU-only in this install |
| GPU hardware present on this dev machine | Yes — RTX 3050, confirmed via `nvidia-smi`, currently idle and entirely unused by this project |
| CUDA toolkit / cuDNN installed | **Not installed** — this is the CPU-only PyTorch wheel; no CUDA runtime is present or required for it |

**This project runs entirely on CPU today, by explicit build choice, not by hardware
limitation.** There is no CUDA version this document can meaningfully "pin" because no CUDA build
is in use anywhere in this dependency set. If GPU acceleration is ever adopted (see
`docs/MODIFICATION_COOKBOOK.md` entry 24 for the full how-to and its caveats), the correct
procedure is to consult [PyTorch's own install matrix](https://pytorch.org/get-started/locally/)
for a CUDA-toolkit-version-matched wheel at that time — this document deliberately does not
pre-guess a CUDA version, since doing so without a GPU build actually installed and tested would
be exactly the kind of unverified claim this audit is trying to avoid making.

### Important native (non-Python-package) libraries

| Library | Exact version, this dev machine | How it's required | Pinning status |
|---|---|---|---|
| **FFmpeg** | `8.1.2-essentials_build-www.gyan.dev` (confirmed live: `ffmpeg -version`) | Every audio-touching path shells out to the `ffmpeg`/`ffprobe` binaries via `subprocess` — not a pip package, must be on `PATH` | **Not pinned anywhere in the repo.** `docs/SETUP.md` documents installing "FFmpeg" with no version requirement; `Dockerfile.worker` installs whatever `apt-get install ffmpeg` resolves to on Debian at build time (typically an *older* FFmpeg than this gyan.dev "essentials" build). See "What should be pinned" below. |
| **PortAudio** (via the `sounddevice` pip package) | Bundled inside the `sounddevice` wheel (`0.5.5`) — not a separate system install on Windows | `scripts/record_test_audio.py`'s mic capture only; not used by the backend/worker at all | Pinned indirectly via `sounddevice`'s own wheel — fine as-is, no action needed |
| **libsndfile** (via the `soundfile` pip package) | Bundled inside the `soundfile` wheel (`0.14.0`) | `backend/services/audio_service.py`'s `load_waveform()` (`sf.read()`) | Pinned indirectly via `soundfile`'s own wheel — fine as-is |
| **CTranslate2** | `4.8.1` (a pip package, but wraps a compiled native inference engine) | Faster-Whisper's actual inference runtime | Pip-installed, unpinned in requirements files (see above) |
| CUDA / cuDNN | Not installed | N/A — CPU-only build in use | N/A |

## Flutter / frontend

### Flutter & Dart SDK

| | Value | Source |
|---|---|---|
| Flutter SDK, this dev machine | **3.47.2 (stable channel)** | `flutter --version`, run live this pass |
| Dart SDK (bundled with the above) | **3.13.2** | `dart --version`, run live this pass |
| Declared SDK constraint | `sdk: ^3.13.2` | `android/pubspec.yaml`'s `environment:` block — a caret range, meaning `>=3.13.2 <4.0.0` |
| CI-pinned Flutter version | **3.47.2**, exact (not floating `channel: stable`) | `.github/workflows/ci.yml`'s `subosito/flutter-action@v2` step, with its own comment explaining exactly why: *"avoids spurious CI-only failures from a newer stable release landing between runs"* |

**This is the one place in the whole repo that already does exactly the right thing for
reproducibility on the SDK-version axis**: CI pins the exact Flutter version this project was
built and verified against, rather than floating on `stable`.

### `pubspec.yaml` — declared dependency constraints

| Package | Constraint | Style |
|---|---|---|
| `cupertino_icons` | `^1.0.8` | caret range |
| `http` | `^1.6.0` | caret range |
| `web_socket_channel` | `^3.0.3` | caret range |
| `flutter_secure_storage` | `10.3.1` | **exact pin** |
| `provider` | `^6.1.5+1` | caret range |
| `record` | `^7.1.1` | caret range |
| `permission_handler` | `13.0.2` | **exact pin** |
| `path_provider` | `^2.1.6` | caret range |
| `share_plus` | `^13.3.0` | caret range |
| `intl` | `^0.20.3` | caret range |
| `shared_preferences` | `^2.5.5` | caret range |
| `flutter_lints` (dev) | `^6.0.0` | caret range |

Two packages (`flutter_secure_storage`, `permission_handler`) are already hard-pinned to an exact
version in `pubspec.yaml` itself — everything else uses a caret range, Dart/Flutter's own
conventional style (allows patch/minor bumps, blocks the next major).

**A real, already-solved environment/tooling gap is documented directly in `pubspec.yaml`
itself** (verbatim, this repo's own comment): `permission_handler_android` 14.x requires
`compileSdk 37`, but this dev machine's Android SDK auto-installer mis-named that platform as
`"android-37.0"` instead of the `"android-37"` Gradle actually looks for (confirmed live this
pass: `C:\Users\natha\AppData\Local\Android\sdk\platforms\` contains exactly `android-35`,
`android-36`, and `android-37.0`) — a real, environment-specific naming defect, not something to
build around at the app level. `dependency_overrides:` pins `permission_handler_android: 13.0.1`,
the last version compiled against `compileSdk 36`, which *is* correctly installed. **Do not remove
this override** without first either fixing the SDK platform naming on the target machine or
confirming a newer Android SDK Manager release has fixed the auto-install naming itself.

### `pubspec.lock` — exact resolved versions (the real reproducibility guarantee)

`android/pubspec.lock` exists, is tracked in git (not excluded by `.gitignore`), and pins **all
100** resolved packages (11 direct + 89 transitive) to exact versions. This is what
`flutter pub get` actually installs — the ranges in `pubspec.yaml` above are only the *allowed*
range; the lockfile is the *actual* pinned reproducibility record. Direct dependencies' locked
versions, confirmed by parsing the lockfile directly this pass:

| Package | Locked version |
|---|---|
| `flutter_secure_storage` | 10.3.1 |
| `provider` | 6.1.5+1 |
| `record` | 7.1.1 |
| `permission_handler` | 13.0.2 |
| `permission_handler_android` | 13.0.1 (the override, confirmed actually in effect) |
| `path_provider` | 2.1.6 |
| `share_plus` | 13.3.0 |
| `intl` | 0.20.3 |
| `shared_preferences` | 2.5.5 |
| `http` | 1.6.0 |
| `web_socket_channel` | 3.0.3 |
| `cupertino_icons` | 1.0.9 |
| `flutter_lints` | 6.0.0 |

**No action needed here** — this is already a correctly reproducible lockfile setup. The only
standing rule: never hand-edit `pubspec.lock`; let `flutter pub get`/`flutter pub upgrade` manage
it, and commit the resulting lockfile change deliberately, not as a side effect of something else.

## Android native toolchain

| Component | Exact version, this dev machine | Source |
|---|---|---|
| Java/JDK | **23.0.1** (`build 23.0.1+11-39`, HotSpot) | `java -version`, run live this pass |
| Gradle wrapper | **9.3.1** (`-all` distribution) | `android/android/gradle/wrapper/gradle-wrapper.properties` |
| Android Gradle Plugin (AGP) | **9.1.0** | `android/android/settings.gradle.kts`: `id("com.android.application") version "9.1.0"` |
| Kotlin Gradle plugin | **2.4.0** | `android/android/settings.gradle.kts`: `id("org.jetbrains.kotlin.android") version "2.4.0"` |
| Java bytecode target | **17** (`JavaVersion.VERSION_17`, `JvmTarget.JVM_17`) | `android/android/app/build.gradle.kts`'s `compileOptions`/`kotlin { compilerOptions }` blocks — targeted even while building with a JDK 23 host JVM, a combination confirmed to produce a working debug build on this machine (`CLAUDE.md`) |
| `compileSdk` / `minSdk` / `targetSdk` | **Not hardcoded in this repo** — set to `flutter.compileSdkVersion`/`flutter.minSdkVersion`/`flutter.targetSdkVersion`, resolved by the Flutter SDK's own Gradle plugin (version 3.47.2's bundled values) at build time | `android/android/app/build.gradle.kts` |
| Installed Android SDK platforms, this dev machine | `android-35`, `android-36`, `android-37.0` (confirmed live) | `%LOCALAPPDATA%\Android\sdk\platforms\` |
| NDK version | `flutter.ndkVersion` — same "resolved by the Flutter SDK, not hardcoded here" pattern as compileSdk | `android/android/app/build.gradle.kts` |

Because `compileSdk`/`minSdk`/`targetSdk`/`ndkVersion` are all sourced from the Flutter SDK's own
bundled Gradle plugin rather than hardcoded in this repo, **pinning the exact Flutter version (as
CI already does) is what actually pins these** — there is no separate number in this repo to lock
beyond that. This is a real, if indirect, dependency chain worth knowing: change the CI/dev
Flutter version and these Android SDK-level values can silently move with it (exactly the failure
mode the `permission_handler_android` override above is a documented instance of).

## Docker & CI pinning status

| Image / tool | Declared as | Actual pinning |
|---|---|---|
| `deployment/Dockerfile.api` base | `python:3.11-slim` | Floats to the latest `3.11.x` patch + whatever Debian base is current "slim" at build time |
| `deployment/Dockerfile.worker` base | `python:3.11-slim` | Same as above |
| `deployment/Dockerfile.worker`'s `ffmpeg` | `apt-get install -y --no-install-recommends ffmpeg` | **Fully unpinned** — whatever version is in that Debian base's `apt` repos at build time. **Not verified to match, or even be close to, this dev machine's FFmpeg 8.1.2** — Debian stable's repos commonly lag several major FFmpeg versions behind a Windows "essentials" build from gyan.dev. This is the single largest unverified version-skew risk in this whole audit: the Docker worker image has never actually been built (`CLAUDE.md`'s own Status Report: "WRITTEN, NEVER ACTUALLY BUILT"), so whether the pipeline even behaves the same under a much older FFmpeg is genuinely unknown. |
| `deployment/docker-compose.yml`'s `postgres` | `postgres:16-alpine` | Floats to latest `16.x` |
| `deployment/docker-compose.yml`'s `redis` | `redis:7-alpine` | Floats to latest `7.x` |
| `.github/workflows/ci.yml`'s `postgres` service | `postgres:16-alpine` | Same floating behavior, but this one **is** actually exercised (CI runs the full test suite against it — see `CLAUDE.md`'s Production Architecture section) |
| `.github/workflows/ci.yml`'s `redis` service | `redis:7-alpine` | Same |
| `.github/workflows/ci.yml`'s Python | `actions/setup-python@v5` with `python-version: "3.11"` | Floats to latest `3.11.x` |
| `.github/workflows/ci.yml`'s Flutter | `subosito/flutter-action@v2` with `flutter-version: '3.47.2'` | **Exact pin** — the one fully-locked tool version in CI |
| `.github/workflows/ci.yml`'s `ffmpeg` | `sudo apt-get install -y ffmpeg` (Ubuntu runner) | **Fully unpinned**, same risk class as the Docker worker image — and this is the FFmpeg version the actual CI test suite (including `tests/test_audio_denoise.py`) runs against, meaning **CI's own FFmpeg version has never been cross-checked against this dev machine's 8.1.2** |

## What should be pinned — specific, minimal recommendations

The goal stated for this audit is **preserving the current working environment, not
modernizing it** — every recommendation below is written to lock in *exactly what's already
proven to work on this machine*, not to bump anything to a newer version.

1. **Generate a real lockfile-equivalent for the currently-working Python environment, without
   changing `requirements*.txt`'s existing unpinned style.** The safest way to do this without
   disturbing the "intentionally unpinned while in flux" development flow: add a **fourth** file,
   e.g. `requirements-lock.txt`, generated via `pip freeze` (filtered to just the top-level
   packages this project actually imports — the list already enumerated above under "Exact
   installed versions") and used **only** for a "known-good, exactly reproduces this dev machine"
   install path (`pip install -r requirements-lock.txt`), documented as such in
   `docs/SETUP.md`/`docs/SETUP_AUTOMATION.md`. This preserves the existing unpinned files exactly
   as-is (so ongoing development isn't disrupted) while giving anyone who needs an *exact*
   reproduction (a grader, a second machine, a disaster-recovery rebuild) a real option. This
   document's "Exact installed versions" section above is the content such a file would contain.
2. **Pin `torch`/`torchaudio`/`faster-whisper`/`ctranslate2` specifically, even if nothing else
   in `requirements-worker.txt` gets pinned.** These four are the ones most likely to silently
   change behavior (accuracy, speed, or outright break) on a version bump, and are exactly the
   four this project has the most invested in keeping stable (measured RTF numbers, a documented
   CPU-only build). Minimum viable version of this recommendation:
   ```
   torch==2.13.0
   torchaudio==2.11.0
   faster-whisper==1.2.1
   ctranslate2==4.8.1
   ```
   added to `requirements-worker.txt`/`requirements.txt` (their currently-bare lines already name
   these packages — this only adds the `==` a fresh install today has zero guarantee of matching).
3. **Pin the FFmpeg version used in `Dockerfile.worker` and `.github/workflows/ci.yml` to match
   this dev machine's proven-working 8.1.2, or at minimum pin to a specific Debian/Ubuntu release
   whose repo FFmpeg version is known and recorded.** This is the highest-value fix in this whole
   audit precisely because it's currently the least verified: the worker Docker image has never
   even been built, so an untested FFmpeg version-skew could be silently baked into it. Concretely,
   either (a) install a specific FFmpeg release directly in the Dockerfile (e.g. a pinned static
   build tarball, bypassing `apt`'s floating version entirely), or (b) at minimum pin the Debian
   base image to a specific tag (`python:3.11.9-slim-bookworm` rather than floating
   `python:3.11-slim`) so the `apt` FFmpeg version is at least reproducible build-to-build, even if
   it still doesn't match this dev machine's Windows FFmpeg build.
4. **Pin `postgres:16-alpine` and `redis:7-alpine` to exact tags** (e.g. `postgres:16.6-alpine`,
   `redis:7.4-alpine` — using whatever exact patch versions CI last ran successfully against, not
   arbitrary newer ones) in both `docker-compose.yml` and `ci.yml`, for the same "don't let a
   background image update silently change behavior between runs" reason the Flutter version is
   already pinned exactly.
5. **Pin `python-version` in CI to a specific patch** (`"3.11.9"`, matching this dev machine and
   both Dockerfiles' effective target) instead of the floating `"3.11"` — a minimal, low-risk
   change since `actions/setup-python` already supports exact versions with no behavior change to
   the workflow's structure.
6. **Add a minimal `pyproject.toml` whose only job is declaring `requires-python = ">=3.11,<3.12"`**
   (or similar) — currently nothing in the repo declares even that much machine-readably; today
   it's tribal knowledge in `CLAUDE.md`'s prose only. This does not require adopting Poetry/PDM/
   any build backend — a `[project]` table with just `requires-python` is valid and immediately
   useful to tooling (IDEs, `pip`, CI) without changing how dependencies are installed at all.
7. **Do not touch `android/pubspec.lock` or its pinning style** — it is already correct. The only
   action item there is procedural: keep committing it deliberately whenever `flutter pub get`/
   `upgrade` changes it, same as today.
8. **Investigate and either remove or explicitly document the five undeclared installed
   packages** (`pyrnnoise`, `audiolab`, `passlib`, `python-docx`, `python-dotenv`) in this specific
   `.venv` — not because they're harmful, but because their presence makes this one `.venv`
   subtly different from what a fresh install produces, which is exactly the kind of
   "works on my machine" gap a reproducibility audit exists to surface. `pip uninstall` is safe
   for all five (confirmed zero imports); doing so is optional, not required, since a fresh
   install already correctly excludes them.

None of the above requires bumping a single package to a newer version than what's already
proven working on this machine — every suggested pin uses this machine's own currently-installed,
currently-working version number.
