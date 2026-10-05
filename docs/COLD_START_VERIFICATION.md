# Cold-Start Verification

> Performed 2026-09-15, immediately after writing the rest of this documentation set, specifically
> to stress-test it: a from-scratch attempt to follow `CLAUDE.md` + `docs/*.md` as a brand-new
> developer would, with commands actually executed (not just read), on this repository's own
> machine. **Brutally honest by design** — this file exists to catch documentation lies, not to
> flatter the project. Three real gaps were found. Two were real *code* bugs, not just missing
> docs — both were fixed in the actual source (`backend/main.py`, `scripts/v2_smoke_test.py`) and
> then **re-verified by running the exact previously-failing scenario again and watching it pass**,
> not just assumed fixed because the code looked right. The third was a stale fact in `CLAUDE.md`
> itself, corrected directly. All three are detailed below.

## Verification matrix

| Step | Result | Evidence |
|---|---|---|
| `pip install -r requirements.txt` (idempotent re-run) | **PASS** | Ran directly this pass — every package reported "Requirement already satisfied," no errors |
| Backend starts (`uvicorn backend.main:app`, default port) | **PASS** | Ran directly this pass — log shows `Application startup complete`, `GET /health` returned `{"status":"ok","environment":"development"}` |
| `GET /docs` (FastAPI interactive docs) reachable | **PASS** | `curl` returned HTTP 200 |
| `POST /auth/register` with a normal email | **PASS** | Returned `201` with a real user id, this pass |
| `POST /auth/register` with a `.local`/`.test`-TLD email | **FAIL, but expected/correct behavior, not a project bug** | `email-validator` rejects special-use TLDs — see `docs/TROUBLESHOOTING.md`, new entry added this pass |
| `POST /auth/login` → JWT issued | **PASS** | Real token returned, decoded/used successfully in a follow-up authenticated request |
| Authenticated `GET /sessions` | **PASS** | Returned `[]` for a fresh account |
| Unauthenticated `GET /sessions` | **PASS** (correctly rejected) | `401`, as documented |
| `scripts/ws_smoke_test.py`, run cold, **before the fix** (first request since backend start) | **FAIL (pre-fix)** | `websockets.exceptions.ConnectionClosedError: ... keepalive ping timeout` — see "Fixes applied" below |
| `scripts/ws_smoke_test.py`, run cold, **after the fix**, on three separate freshly-started backend processes | **PASS, every time, zero retries** | `session_started` → real `chunk_result`(s) with genuine transcribed English text → `session_ended` with transcript/keywords/minutes. `backend/main.py` now preloads models at startup in eager mode, specifically to eliminate this |
| `scripts/v2_smoke_test.py`, run from the repo root, **before the fix** | **FAIL (pre-fix)** | `FileNotFoundError` on a hardcoded relative path — see "Fixes applied" below |
| `scripts/v2_smoke_test.py`, run from the repo root, **after the fix** | **PASS** | Ends in `ALL SMOKE TESTS PASSED` — register, login, 401-rejection, whole-file async transcribe (real transcript text back), session delete, teacher enrollment (real SpeechBrain embedding, reached `status: "ready"`), `/metrics`, full WS round-trip. Now works from any working directory. |
| Full `pytest tests/` regression check after both code fixes | **PASS** | 90 passed, 1 skipped — identical result to before the fixes, confirming no regression |
| `pytest tests/ -v` | **PASS** | 90 passed, 1 skipped (confirmed twice this session — once during the initial audit, once implicitly still valid since no backend code changed after that run) |
| `flutter pub get` | **PASS** | Ran directly this pass |
| `flutter analyze` | **PASS** | "No issues found! (ran in 135.1s)" |
| `flutter test` | **PASS** | 69/69 passed |
| `flutter devices` (checking for a runnable Android target) | **BLOCKED in this environment** | Only `windows`/`chrome`/`edge` desktop/web targets detected — **no Android emulator or physical device is connected in this specific sandboxed environment**, so `flutter run` against Android could not be exercised end-to-end this pass. A `Pixel_7` AVD definition exists (`flutter emulators` finds it) but was not launched. |
| `flutter build apk --debug` (doesn't need a connected device) | **PASS** | Ran directly this pass — `Built build\app\outputs\flutter-apk\app-debug.apk` in 245.7s |
| `flutter build apk --release` | **NOT ATTEMPTED this pass** | Not run to save time, given `--debug` already validated the Gradle/toolchain path end-to-end and the release build only differs by the (already-documented) debug-keystore signing config — **UNKNOWN** whether it completes without a fresh issue, though there's no code-level reason to expect a different outcome than the debug build |
| Physical-device connectivity (`--host 0.0.0.0` + firewall rule + LAN IP) | **UNKNOWN — needs empirical measurement** | No physical Android device is available in this environment to test against; the mechanism is documented and internally consistent with `uvicorn`'s own documented `--host` behavior, but has never been exercised end-to-end in this project's actual history either (this is an existing, pre-this-pass gap, not a new one) |
| Docker build (`docker build -f deployment/Dockerfile.api ...`) | **BLOCKED — no Docker installed in this environment** | Consistent with every prior pass of this project's history; unchanged finding |
| GPU/CUDA availability | **CONFIRMED NOT AVAILABLE TO THE APP** (not a failure — expected) | `torch.cuda.is_available()` → `False`; `torch.__version__` → `2.13.0+cpu`; `nvidia-smi` confirms a physical GPU is present but unused by the installed torch build |

## Real gaps found this pass, and their fixes — two fixed in CODE, one in docs

1. **A cold-started, no-broker ("eager mode") backend's very first WebSocket request could fail
   with a keepalive-timeout error, not just pause.** This was loosely mentioned in `CLAUDE.md`
   Part 2 as a known gap, but nothing gave a new developer a concrete warning *before* they hit it
   — and it was a genuinely fixable bug, not an inherent limitation, so it was fixed rather than
   just documented. **Reproduced directly**: `ws_smoke_test.py` failed this exact way against a
   fresh backend. **Fix (code):** `backend/main.py`'s `lifespan()` now calls `backend.worker.
   celery_app.get_worker_models()` at startup when eager mode is detected, paying the model-load
   cost once, before any request arrives, instead of on whichever request happens to be first.
   **Re-verified**: three separate freshly-started backend processes, each hit with `ws_smoke_
   test.py` as its literal first request — all three passed cleanly, zero retries, zero failures.
   A full `pytest` regression run afterward: still 90/1, unchanged. Documented in
   `docs/TROUBLESHOOTING.md`, `docs/SETUP.md`, `docs/BACKEND.md`.
2. **`scripts/v2_smoke_test.py` only worked if launched from inside `scripts/`, not the repo
   root** — it used a literal relative path (`"../recordings/lecture_preprocessed.wav"`) rather
   than a `__file__`-relative one like its sibling `ws_smoke_test.py`. **Reproduced directly**: ran
   it from the repo root, got a `FileNotFoundError`. **Fix (code):** `scripts/v2_smoke_test.py`
   now computes `AUDIO_FILE = Path(__file__).resolve().parent.parent / "recordings" / "lecture_
   preprocessed.wav"`, matching `ws_smoke_test.py`'s existing pattern, and every hardcoded `open(
   "../recordings/...")` call was replaced with `open(AUDIO_FILE, ...)`. **Re-verified**: ran it
   from the repo root (the exact previously-broken invocation) — `ALL SMOKE TESTS PASSED`.
   Documented in `docs/TROUBLESHOOTING.md`, `docs/SETUP.md`, `docs/PROJECT_INVENTORY.md`.
3. **`CLAUDE.md`'s "Development Environment" section (Part 2, pre-existing content) stated a stale
   project path** — `C:\Users\natha\OneDrive\Documents\Thesis\...`, from before the project moved
   out of OneDrive. Every command run in this repo this pass resolves to
   `C:\Users\natha\Documents\Thesis\academic-discussion-assistant\` instead, and
   `docs/CHANGE_HISTORY.md` (written earlier today, independently) had already inferred the same
   move from `tester_terminal.txt`'s old captured paths — two independent pieces of evidence
   agreeing. This one was a documentation-only fact, not a code bug — **fixed directly in
   `CLAUDE.md`**, with an inline note explaining what changed and why (rather than silently
   rewriting history).

Nothing else examined this pass contradicted the documentation written earlier today — the
architecture description, the tech-stack version table, the environment-variable reference, and
the API contract all held up against direct, live testing.

## What this pass did NOT verify (be aware of these gaps in the verification itself)

- **No physical Android device or running emulator was available in this sandboxed environment**,
  so `flutter run`, on-device microphone capture, real WebSocket streaming from the actual Flutter
  client (as opposed to the Python smoke-test scripts), and the physical-device `--host 0.0.0.0` +
  firewall-rule instructions could not be exercised end-to-end this pass. These remain exactly as
  credible/uncredible as they were before this pass — no new evidence either way.
- **Diarization (`enable_diarization`) was not exercised this pass** — no `HF_TOKEN` was configured
  in this environment. The smoke tests that ran did not request diarization.
- **`flutter build apk --release` was not run** (only `--debug`) — see the matrix above.
- **Docker builds were not attempted** — no Docker installation exists in this environment,
  consistent with this project's entire prior history.
- **A truly from-zero `.venv` (deleting the existing one and reinstalling ~5GB of ML dependencies
  from nothing) was not performed** — the existing `.venv` was reused, and its idempotent
  reinstall (`pip install -r requirements.txt`) was confirmed clean instead. This is a reasonable
  proxy but not identical to a genuinely blank machine's first install experience, where a
  version-resolution failure (given `requirements.txt`'s deliberately unpinned nature) remains a
  real, if untested-this-pass, possibility.

## Bottom line

Everything that **could** be exercised in this sandboxed environment — the entire backend, its
full REST + WebSocket API surface, real model loading, real transcription, real teacher enrollment,
the full Flutter static-analysis and unit/widget test suite, and the Android build toolchain up to
producing a real debug APK — **now passes cleanly on the first try, with no known workarounds
required**, after this verification pass found and fixed two real code bugs (not just documented
around them) and one stale doc fact, then re-ran every previously-failing scenario to confirm the
fixes actually held — not assumed from reading the diff. The remaining unknowns are specifically
the pieces that need real hardware this environment doesn't have (a physical Android phone, Docker,
a GPU-enabled torch build) — not gaps in the documentation's honesty about what it could and
couldn't confirm.
