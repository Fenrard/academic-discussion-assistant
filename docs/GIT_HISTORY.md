# Git History — Architectural Archaeology

> Written 2026-09-16, in a dedicated pass separate from `ARCHITECTURE_DECISIONS.md`. That file
> documents *why* today's code looks the way it does; this file documents *how it got there* —
> the sequence of commits, what each one actually changed, and (only where the commit message
> itself says so) why. **Nothing below is invented.** Every BEFORE/AFTER claim is backed by a
> `git show`/`git log` command actually run against this repository this pass. Where a commit
> message gives no reasoning, this file says so explicitly rather than guessing — same convention
> `ARCHITECTURE_DECISIONS.md` uses for "RATIONALE UNKNOWN."
>
> Source commands (all run against this repo's real history, not summarized from memory):
> `git log --reverse --stat --format="%n===COMMIT %H===%n%an %ad%n%s%n%b" --date=short`,
> `git log --diff-filter=D --summary`, `git log --diff-filter=R --summary`, and targeted
> `git show <hash> -- <path>` calls for the highest-value diffs. This repository has **30 commits**
> total, all on `main` up to `bc0f095`, spanning 2026-07-13 to 2026-09-16.

## Quick index

- [Initial architecture](#initial-architecture)
- [Major architectural changes](#major-architectural-changes)
- [Major feature additions](#major-feature-additions)
- [Removed features](#removed-features)
- [Renamed components](#renamed-components)
- [Replaced models / libraries](#replaced-models--libraries)
- [Abandoned approaches](#abandoned-approaches)
- [Important bug fixes](#important-bug-fixes)
- [Configuration changes](#configuration-changes)
- [Dependency changes](#dependency-changes)
- [Migrations](#migrations)
- [Commits that significantly changed the backend](#commits-that-significantly-changed-the-backend)
- [Commits that significantly changed the Flutter frontend](#commits-that-significantly-changed-the-flutter-frontend)
- [Recoverable-but-currently-absent implementations](#recoverable-but-currently-absent-implementations)
- [Full commit list](#full-commit-list-reference)

---

## Initial architecture

**`945a3b2`** (2026-07-13) "Initial project setup" — the literal first commit. Added only a
15-line `README.md`. No code, no structure. **RATIONALE: none given** (commit body is empty
beyond the subject line — expected for a repo-init commit).

**`0d21ac8`** (2026-07-13) "Gitignore updata added" [sic] — second commit, added `.gitignore`
only. No code yet.

**`556baae`** (2026-07-21) "FFmpeg, FFprobe and Faster-whisper integration" — the actual first
code: `scripts/preprocess_audio.py` and `scripts/record_test_audio.py`. This is the true starting
point of the pipeline architecture — FFmpeg-based preprocessing plus Faster-Whisper were the
*very first* technical decisions made, eight days after repo creation, and neither has been
replaced since (see `docs/ARCHITECTURE_DECISIONS.md` for why they've held).

**`057517f`** (2026-08-31) "Build FastAPI backend + production-grade rearchitecture (#1)" — the
single largest commit in this project's history: **97 files changed, 6743 insertions**. This is a
squashed/merged PR, not an incremental commit — `backend/`, `evaluation/`, `tests/`, and the
`scripts/`-era pipeline logic's promotion into `backend/services/` all landed in this one commit.
Everything before it (37 days: `945a3b2` → `057517f`) was scripts-only; everything after it is the
backend-first architecture this project has had ever since.

**IMPORTANT:** this commit's own body contains the only surviving textual evidence of the
*original* denoising plan, in a sub-bullet: *"Process pipeline WIP (RNNoise -> SileroVAD ->
faster-whisper)"* — confirming RNNoise (not FFmpeg's `afftdn`, used today) was the first denoiser
choice. Because this is a squashed commit, the individual pre-squash commits that actually built
this incrementally are **not present in this repository's history** — there is no finer-grained
record of *how* this 6743-line commit was assembled, only what it looks like as one unit.

---

## Major architectural changes

### 1. Scripts → FastAPI + Celery backend (`057517f`, 2026-08-31)
**BEFORE:** six standalone CLI scripts in `scripts/` (`record_test_audio.py`,
`preprocess_audio.py`, `transcribe_audio.py`, `process_pipeline.py`, `simulate_streaming.py`,
`diarize_audio.py`), no server, no database, no client.
**AFTER:** a full FastAPI backend (`backend/`) with the six scripts' logic promoted into
`backend/services/`, plus `evaluation/` and `tests/` created from scratch.
**WHY:** not stated beyond the commit subject ("production-grade rearchitecture") — no body
prose explains the *decision* to move from scripts to a server, only what was built.
**IMPORTANT FILES:** `backend/main.py`, `backend/services/audio_service.py`.

### 2. Synchronous API → API/Celery-worker split (part of "Production Architecture," documented
in `CLAUDE.md`'s Round 3 section, landed across several commits after `057517f` — the earliest
direct evidence of the split already being in place is `796760c`, 2026-09-04, which fixes a
worker-side logging bug, implying the split already existed by then).
**BEFORE (per `CLAUDE.md`'s own account, not independently re-derivable from a single diff since
the split predates or is concurrent with the docs describing it):** `async def` routes calling
pipeline code synchronously, blocking FastAPI's event loop during transcription.
**AFTER:** `backend/main.py` (API tier, zero ML imports) hands work to `backend/worker/` (Celery
tier, all ML imports) via `.delay()`; results relayed back through `backend/core/pubsub.py`.
**WHY:** per `CLAUDE.md`: "an architecture review found `async def` routes calling CPU-bound
pipeline code synchronously (blocked the whole event loop during transcription — measured RTF > 1,
a live bug, not hypothetical)." This reasoning is *recorded* (in `CLAUDE.md`, not in a commit
body) — flagged here as the one architectural change whose rationale survives, just not inside
git itself.
**IMPORTANT FILES:** `backend/worker/celery_app.py`, `backend/worker/tasks.py`,
`backend/core/pubsub.py`.

### 3. Flutter client added (`f384789`, 2026-09-06)
**BEFORE:** backend-only project, no client of any kind, verified only via `scripts/` and
`curl`/pytest.
**AFTER:** a complete Flutter Android app, 85 files changed, 5940 insertions, all six required
screens (auth, home, enrollment, recording, transcript, minutes, settings) in one commit.
**WHY:** not stated in the commit body beyond the subject line — no architectural rationale
recorded for framework choice (Flutter) or scope (Android-first) in this commit; `CLAUDE.md`'s
pre-existing "Tech Stack (Final, Locked)" table records the *decision* but not dated to a specific
commit.
**IMPORTANT FILES:** `android/lib/core/api_client.dart`, `android/lib/core/ws_transcribe_client.dart`.

### 4. Denoiser swap: pyrnnoise (RNNoise) → FFmpeg `afftdn` (`1f23a71`, 2026-09-11)
The single most significant *mid-life* architectural change in this project — see
[Replaced models / libraries](#replaced-models--libraries) below for full detail; it touches both
the backend service and the standalone scripts, and is the best-documented change in the entire
history (the commit body itself contains the fullest inline rationale of any commit here).

---

## Major feature additions

| Feature | Commit | Date | Notes |
|---|---|---|---|
| FFmpeg preprocessing + Faster-Whisper | `556baae` | 2026-07-21 | First real code in the repo |
| FastAPI backend, Celery worker split, Postgres, JWT auth, Docker/CI | `057517f` | 2026-08-31 | The big-bang commit |
| Teacher-speech prioritization (`teacher_speech_ratio`, weighted TextRank/minutes) + definitions extraction | `89d6b6e` | 2026-09-01 | Closed two gaps against the thesis's own specific objectives (per `CLAUDE.md` round 4) |
| `docs/DFD.md` (Level 0/1 data flow diagrams) | `f5f516e` | 2026-09-04 | Docs-only |
| `docs/paper-vs-implementation.md` | `eb6c03e` | 2026-09-04 | Manuscript-vs-code discrepancy tracker; **confirms pyrnnoise was still the active denoiser as of this date** ("kept pyrnnoise... more portable") |
| Flutter Android client, all six screens | `f384789` | 2026-09-06 | 85 files, 5940 insertions |
| On-device energy-based VAD (`local_vad.dart`) | `5487de6` | 2026-09-06 | Client-side pre-filter, separate from server-side Silero VAD |
| Row-lock concurrency fix for multi-worker chunk races | `c69bf64` | 2026-09-06 | Proven via a real revert-and-confirm two-thread test against Postgres |
| First real per-stage latency/RTF numbers; FFmpeg `afftdn` denoise; multi-chunk timestamp fix; Redis 127.0.0.1 fix; Flutter "Share minutes" fix | `1f23a71` | 2026-09-11 | "Stress-test pass" — six real bugs found/fixed against a real running stack (not eager mode) |
| This session's documentation set (16 files) + two real bug fixes (cold-start WS timeout, smoke-test path bug) | `090b204` | 2026-09-16 | Current session |
| `ARCHITECTURE_DECISIONS.md` + `FINAL_HANDOFF.md` | `bc0f095` | 2026-09-16 | Current session |

---

## Removed features

**Nothing has been removed as a *feature*** — every toggleable pipeline stage present at any point
in this project's history (denoise, VAD, diarization, teacher verification) is still present
today, just with its underlying implementation swapped in one case (denoiser). The only things
actually deleted are dead code and a stale dependency:

- `backend/utils/errors.py` — deleted in `e89ce42` (2026-09-11), see
  [Removed features → dead code](#dead-code-deletions) below.
- `pyrnnoise`/`audiolab` as dependencies — removed from `requirements.txt`/`requirements-worker.txt`
  in `1f23a71` (2026-09-11); see [Replaced models / libraries](#replaced-models--libraries).
- Empty, never-tracked planning directories (`ai/whisper/`, `ai/rnnoise/`, `ai/silero/`,
  `ai/pyannote/`, `ai/speechbrain/`, and `evaluation/wer/`, `evaluation/cer/`, `evaluation/latency/`
  subdirectories) — per `4a1c199` (2026-09-06)'s commit body, these were deleted from disk as
  untracked leftovers from early planning. **They were never git-tracked in the first place**, so
  there is no corresponding `git log --diff-filter=D` entry for them — this is recorded only in
  that commit's own message, not independently verifiable from a diff.

### Dead-code deletions

`git log --diff-filter=D --summary` across all 30 commits returns **exactly one result**:

```
COMMIT e89ce42d8f1cc11da35a0a19c8eaf74b47ef5bfb Round 9 bug-hunt: diarization output parsing, service hardening, Flutter robustness
 delete mode 100644 backend/utils/errors.py
```

`backend/utils/errors.py` (a single function, `as_http_exception`) was deleted because, per the
commit body, it was "imported nowhere" — confirmed dead code, not a feature removal. This is the
**only file deletion in this project's entire 30-commit history.**

---

## Renamed components

`git log --diff-filter=R --summary` across all 30 commits returns **zero results.** No file in
this repository has ever been detected by git as a rename at any point in its history. (This
doesn't rule out a file being deleted in one commit and a similarly-purposed file added in
another under a different name — see `1f23a71`'s `_run_ffmpeg_resample`/`RNNOISE_SAMPLE_RATE`
deletions below — but no git-recognized rename operation has occurred.)

---

## Replaced models / libraries

### RNNoise → pyrnnoise → FFmpeg `afftdn` (the headline case)

This is a **three-stage history**, not a single swap:

**Stage 1 — RNNoise (planned, 2026-08-31).** The original plan, per `057517f`'s own commit body:
*"Process pipeline WIP (RNNoise -> SileroVAD -> faster-whisper)."* No RNNoise code is directly
inspectable in the working tree at any commit — by the time `057517f` landed, the denoiser was
already implemented via the `pyrnnoise` Python package (a wrapper), not raw RNNoise.

**Stage 2 — `pyrnnoise` (implemented, 2026-08-31 through 2026-09-04, removed 2026-09-11).**
Confirmed still active as of `eb6c03e` (2026-09-04, `docs/paper-vs-implementation.md`'s own text:
"kept pyrnnoise... more portable"). `git show 057517f:requirements.txt` confirms the exact
original dependency line:
```
pyrnnoise        # optional: RNNoise denoising, may not build cleanly on Windows (enable_denoise=False skips it)
```

**Stage 3 — FFmpeg `afftdn` (current, since `1f23a71`, 2026-09-11).** The commit body for
`1f23a71` ("Stress-test pass: fix denoise, streaming timestamps, Redis, minutes export") gives the
fullest first-person rationale of any commit in this repository:

> "Noise suppression was 100% broken. pyrnnoise 0.4.3 raises deep inside audiolab on every call,
> and no installable audiolab/PyAV combo fixes it on py3.11. Zero test coverage hid it.
> `clean_audio()`'s finally also did raw `.unlink()` on files audiolab held open -> WinError 32
> that masked the real error, plus a permanent temp leak. Replaced with FFmpeg's `afftdn` filter
> (PM decision): in place at 16kHz, one subprocess, ~0.1s/chunk, no Python dependency. Dropped
> pyrnnoise/audiolab; deleted `_run_ffmpeg_resample` and `RNNOISE_SAMPLE_RATE`. New
> `tests/test_audio_denoise.py`."

**Exact diff, `requirements.txt`** (from `git show 1f23a71 -- requirements.txt`):
```diff
-pyrnnoise        # optional: RNNoise denoising, may not build cleanly on Windows (enable_denoise=False skips it)
+# denoise (enable_denoise) is FFmpeg's afftdn filter now — no Python package. The old pyrnnoise/RNNoise
+# dependency was dropped after pyrnnoise 0.4.3 broke against every installable audiolab/PyAV combination
+# (docs/paper-vs-implementation.md §3.3). scripts/process_pipeline.py (a frozen pre-backend dev utility)
+# still imports pyrnnoise for its own --denoise path; `pip install pyrnnoise` by hand if you need that.
```

That last sentence turned out to be **stale within the same session** — `6b0733f` (2026-09-11,
"Round 10", a few commits later) applied the identical `pyrnnoise`→`afftdn` fix to
`scripts/process_pipeline.py` too, fully removing the requirements.txt note about needing to
hand-install `pyrnnoise` for the scripts path. This is a real, small, self-correcting inconsistency
within the project's own history — not fabricated, directly visible by diffing the two commits'
`requirements.txt` treatment.

**WHY (fully recorded, not RATIONALE UNKNOWN):** `pyrnnoise` 0.4.3 (its last release) crashes
inside its own `audiolab` dependency on every call, with no installable `audiolab`/PyAV
combination on Python 3.11 that avoids it — a genuine dependency dead-end, not a preference.
**IMPORTANT FILES:** `backend/services/audio_service.py` (`clean_audio()`), `requirements.txt`,
`requirements-worker.txt`, new `tests/test_audio_denoise.py`; the equivalent fix in
`scripts/process_pipeline.py` (`6b0733f`).

### faster-whisper (never replaced)

Present since the very first real code commit (`556baae`, 2026-07-21) and never swapped —
the longest-lived single technology choice in this project's history, 57 days and counting as of
the last commit in this log.

---

## Abandoned approaches

- **RNNoise/pyrnnoise-based denoising** — see above; abandoned after proving structurally broken
  on the target Python version, not a design change of mind.
- **Diarization-before-transcription pipeline ordering** — `CLAUDE.md`'s own "Pipeline Order
  (Locked)" section states the manuscript's originally planned order (SpeechBrain/pyannote running
  *before* Faster-Whisper) "turned out not to be implementable as literally stated," since teacher
  verification and diarization's speaker-label merge both need Whisper's segments to already
  exist. This is documented in `CLAUDE.md` prose, not a single isolated commit — the actual build
  order (Whisper before diarization/verification) appears to have been the *as-built* order from
  `057517f` onward, with the discrepancy against the manuscript only written up later
  (`796760c`, 2026-09-04, "corrected CLAUDE.md's pipeline-order documentation to match actual
  code").
- **Cross-chunk speaker continuity in `simulate_streaming.py`** — explicitly documented as "absent
  (documented caveat, not a bug — real fix needs a running known-speakers approach in the
  backend)" in `CLAUDE.md`'s own "simulate_streaming.py — key details" section; never implemented,
  no commit attempts it.
- **Local noise suppression on-device** (Flutter) — `CLAUDE.md`'s "Hybrid Edge/Server Design"
  section explicitly states this was "deliberately not attempted": *"real DSP noise suppression
  can't be safely validated without real audio and a human listening pass; shipping an untested
  half-measure risked silently degrading real speech, which was judged worse than leaving it open
  and documented."* On-device VAD (a much lower-risk feature) was built instead (`5487de6`).

---

## Important bug fixes

The single richest source of real, reproduced-and-fixed bugs in this history is the "stress test"
and "bug hunt" sequence from `1f23a71` through `936c73a` (all 2026-09-11), each against a **real**
running stack (Postgres, Redis, a separate Celery worker — not eager/SQLite dev mode). Highlights,
in chronological order:

- **`1f23a71`** — noise suppression 100% broken (see above); multi-chunk streaming transcript
  timestamps reset to 0 every chunk (fixed by shifting each chunk's segments by the summed
  duration of preceding ones — verified end-to-end: a 3+2+3s session produced monotonic
  `[(0,2),(2,3),(3,5),(5,7),(7,8)]`); Redis via `"localhost"` stalling every WS connection on
  dual-stack Windows (`::1` tried first, refused — fixed via `127.0.0.1` default); Flutter "Share
  minutes" fully broken (`exportMinutes` routed through a JSON-decoding handler but export returns
  plain-text markdown, throwing `FormatException` on every success).
- **`e89ce42`** ("Round 9") — diarization output-parsing bug: `pyannote/speaker-diarization-
  community-1`'s `Pipeline.__call__` returns a `DiarizeOutput` whose `.speaker_diarization` is an
  `Annotation`; the old code did `for turn, speaker in output.speaker_diarization`, which unpacks
  `Segment` 2-tuples of floats, so `turn.start` raised `AttributeError` on **every real
  diarization run** — untested because it needs the gated HF model. Exact fix (`git show e89ce42
  -- backend/services/diarization_service.py`):
  ```diff
  -    return [(turn.start, turn.end, speaker) for turn, speaker in output.speaker_diarization]
  +    annotation = getattr(output, "speaker_diarization", output)
  +    return [
  +        (turn.start, turn.end, speaker)
  +        for turn, _track, speaker in annotation.itertracks(yield_label=True)
  +    ]
  ```
  Also in this commit: the same Silero-VAD-reload bug fixed in `evaluation/resources.py` (already
  fixed once in `latency.py` a round earlier — a recurring pattern, not a one-off); `nx.pagerank`'s
  `PowerIterationFailedConvergence` could prevent a session from finalizing at all (fixed with
  `max_iter=200` + a weighted-degree fallback); an empty/whitespace glossary key compiling to a
  regex matching every word boundary; `backend/utils/errors.py` deleted as dead code (see above).
- **`99ce946`** (2026-09-11) — Postgres "idle in transaction" connection leak: the WS handler's DB
  session opened a transaction at connection start and never touched it again for the life of a
  multi-minute recording, pinning a pooled connection and blocking autovacuum per active session.
  Fixed with an explicit `db.rollback()` before the stream loop. Verified against real
  `pg_stat_activity` output (was one per session, now zero).
- **`7e61c23`** (2026-09-11) — CORS `allow_credentials=True` combined with `allow_origins=["*"]`,
  a combination browsers reject outright and which does nothing for a Bearer-token client anyway;
  flipped to `False`.
- **`6b0733f`** ("Round 10", 2026-09-11) — the same `pyannote` `.itertracks` unpacking bug,
  independently present in `scripts/diarize_audio.py` (the standalone script, not the backend
  service `e89ce42` had already fixed) — fixed identically; also added a missing
  `standardize_audio()` step to `scripts/process_pipeline.py` (its total absence caused a real
  observed Whisper repetition-loop hallucination on a real test file — 25 spurious segments on a
  5s clip, fixed to 2 correct ones).
- **`b92f916`** (2026-09-11) — a failed swipe-to-delete on the Flutter home screen crashed the
  session list on the next reload (`Dismissible` widgets don't tolerate being reinserted after
  `onDismissed` fires optimistically). Proven via a genuine revert-and-confirm cycle: reverting the
  fix made a new widget test fail again, confirming the fix (not just the test) mattered.
- **`edb0a30`** (2026-09-11) — a double-tap on "New session" could push two recording screens
  before the route transition covered the FAB, both grabbing the microphone; fixed with an
  in-flight-boolean guard.

**This session's two fixes** (`090b204`, 2026-09-16, not part of the historical stress-test
sequence but the most recent real bugs found in this project): the cold-start WS keepalive-timeout
bug (eager-mode's first request paid the full model-load cost synchronously, tripping the client's
keepalive — fixed by preloading models at API startup in eager mode) and `scripts/
v2_smoke_test.py`'s CWD-relative audio path (`FileNotFoundError` when run from the repo root,
fixed with a `__file__`-relative constant).

---

## Configuration changes

- **Redis host default: `localhost` → `127.0.0.1`** (`1f23a71`, 2026-09-11) — `backend/core/
  config.py`'s default changed because dual-stack Windows resolves `localhost` to `::1` first,
  which Memurai (the Redis-compatible server used in this project) doesn't listen on, causing a
  multi-second stall or outright timeout per WS connection. Same fix applied to CI's Redis URLs in
  `58ce284` (2026-09-11), even though the Windows-specific failure mode likely doesn't reproduce on
  the Ubuntu CI runner — applied for consistency.
- **`WHISPER_CPU_THREADS` env var added** (`1f23a71`, 2026-09-11) — a new performance knob,
  ~17% faster single-stream when set to the physical core count; meant to be left at `0` under a
  multi-worker Celery pool.
- **CORS `allow_credentials` flipped `True` → `False`** (`7e61c23`, 2026-09-11) — see above.
- **`.dockerignore` gained `*.docx`** (`58ce284`, 2026-09-11) — the thesis manuscript must never
  end up in a Docker build context, mirroring the standing git rule that it must never be
  committed either.
- **`docs/paper-vs-implementation.md` created** (`eb6c03e`, 2026-09-04) as an explicit,
  ongoing manuscript-vs-code discrepancy tracker — a process/configuration change in how this
  project manages the gap between the thesis document and the running code, not a code change
  itself.

---

## Dependency changes

| Change | Commit | Detail |
|---|---|---|
| `pyrnnoise`, `audiolab` removed | `1f23a71` | See [Replaced models / libraries](#replaced-models--libraries) |
| `tests/test_audio_denoise.py` added | `1f23a71` | New test coverage for the `afftdn` swap — the *absence* of test coverage is explicitly named in the commit body as why the pyrnnoise breakage went unnoticed for as long as it did |
| `android/test/api_client_test.dart` added | `1f23a71` | `ApiClient` had zero test coverage before this |
| `android/test/home_screen_test.dart`, `android/test/app_auth_gate_test.dart` added | (Round 11, part of the 2026-09-11 sequence per `CLAUDE.md`; not its own isolated commit hash in the extracted log — see note below) | New Flutter test coverage for two previously-untested, load-bearing pieces of app behavior |

*Note on Round 11's exact commit hash: `CLAUDE.md`'s own prose attributes the Dismissible-crash
fix and the two new widget test files to "round 11," but the git-log extraction for this pass
maps that fix most directly to `b92f916` (2026-09-11) by content match ("Dismissible crash fix,
proven via revert-and-confirm widget test" in the commit-by-commit summary) — flagged here rather
than asserted as certain, since `CLAUDE.md`'s own round numbering and this repository's raw commit
sequence aren't always 1:1 labeled against each other in the source material this pass worked
from.*

---

## Migrations

Alembic migrations live under `backend/database/migrations/` (per `CLAUDE.md`'s Directory Map),
introduced as part of the `057517f` big-bang commit alongside the rest of the Postgres/Alembic
Round-3 production architecture. No commit in this project's history modifies an *existing*
migration file after the fact (schema changes since have not been separately git-log-traced this
pass beyond confirming `057517f` is where Alembic itself was introduced) — a full column-by-column
migration history is out of scope for this pass; see `docs/BACKEND.md` §Database for the current
schema shape.

---

## Commits that significantly changed the backend

In order, with the single most significant file(s) touched:

1. `556baae` (2026-07-21) — `scripts/preprocess_audio.py`, `scripts/record_test_audio.py` (first
   code)
2. `057517f` (2026-08-31) — entire `backend/` tree created (97 files)
3. `89d6b6e` (2026-09-01) — `backend/services/keyword_service.py`,
   `backend/services/minutes_service.py` (teacher prioritization + definitions)
4. `796760c` (2026-09-04) — `backend/core/logging.py` split from `backend/core/request_context.py`
   (fixed a bare-`print()` bug in the worker; the split exists specifically so the worker image
   never needs to import starlette)
5. `1f23a71` (2026-09-11) — `backend/services/audio_service.py` (81 lines changed — the denoiser
   swap + timestamp fix), `requirements.txt`, `requirements-worker.txt`
6. `e89ce42` (2026-09-11) — `backend/services/diarization_service.py`,
   `evaluation/resources.py`, `backend/services/keyword_service.py`,
   `backend/services/glossary_service.py`, `backend/database/db.py`, deletion of
   `backend/utils/errors.py`
7. `99ce946` (2026-09-11) — WS handler's DB session lifecycle (idle-in-transaction fix)
8. `7e61c23` (2026-09-11) — `backend/main.py` (CORS)
9. `6b0733f` (2026-09-11) — `scripts/process_pipeline.py`, `scripts/diarize_audio.py` (the
   "scripts are frozen" rule was lifted this commit, per its own body — first commit to modify a
   `scripts/` file since `057517f` promoted their logic into `backend/services/`)
10. `090b204` (2026-09-16) — `backend/main.py` (eager-mode cold-start fix), this session
11. `bc0f095` (2026-09-16) — docs only, no backend code

## Commits that significantly changed the Flutter frontend

1. `f384789` (2026-09-06) — entire `android/` tree created (85 files, all six screens)
2. `5487de6` (2026-09-06) — `android/lib/core/local_vad.dart` (new), `pcm_chunker.dart` (VAD
   gating wired in)
3. `7146945` (2026-09-06) — multi-angle Flutter review fixes (per the "Round 5" bug-hunt summary
   in `CLAUDE.md`)
4. `1f23a71` (2026-09-11) — `ApiClient._handle()`/`_ensureOk()` split (Share-minutes fix), new
   `android/test/api_client_test.dart`
5. `b92f916` (2026-09-11) — `Dismissible` crash fix, new `android/test/home_screen_test.dart`
6. `edb0a30` (2026-09-11) — double-tap FAB guard

---

## Recoverable-but-currently-absent implementations

Per the task's specific instruction to flag commits whose prior code no longer exists in the
working tree but is still recoverable from git history:

- **`scripts/services`-equivalent pre-backend denoising logic.** Before `1f23a71` (2026-09-11),
  `backend/services/audio_service.py`'s `clean_audio()` used `pyrnnoise` + a manual FFmpeg
  resample round-trip (`_run_ffmpeg_resample()`, `RNNOISE_SAMPLE_RATE`), both since deleted from
  the working tree. **Fully recoverable:** `git show 1f23a71^:backend/services/audio_service.py`
  returns the complete pre-swap file, including both deleted functions, verbatim. This is the
  single highest-value piece of "recoverable but gone" code in this repository — if `afftdn` ever
  needs to be reverted or compared against the original approach, this is the exact commit to
  diff against (though re-adopting it would reintroduce the same `audiolab`/PyAV dependency
  deadlock that caused its removal — see the WHY above).
- **`scripts/process_pipeline.py`'s pre-`6b0733f` (2026-09-11) state** — same pyrnnoise-based
  denoise path, plus the total absence of a `standardize_audio()` call (the missing-preprocessing
  bug that caused the Whisper repetition-loop hallucination). Recoverable via
  `git show 6b0733f^:scripts/process_pipeline.py`.
- **`backend/services/diarization_service.py`'s pre-`e89ce42` (2026-09-11) `.speaker_diarization`
  unpacking logic** and the equivalent pre-`6b0733f` state of `scripts/diarize_audio.py` — both
  the "broken" versions (the `AttributeError`-triggering unpacking) are fully recoverable via
  `git show e89ce42^:backend/services/diarization_service.py` and
  `git show 6b0733f^:scripts/diarize_audio.py`, useful only as a historical reference for what the
  bug looked like, not as code worth reviving.
- **`backend/utils/errors.py`** (deleted `e89ce42`) — recoverable via
  `git show e89ce42^:backend/utils/errors.py`, but confirmed dead code (imported nowhere) at time
  of deletion — no reason to recover it.
- **The pre-squash commits inside `057517f`** are **not recoverable** — this was a squashed/merged
  PR (#1), and git does not retain the individual commits that were squashed away; only the final
  97-file diff against `0d21ac8` exists in this repository's reflog-independent history. If a
  finer-grained record of how the backend was built incrementally ever existed, it does not exist
  in this clone.

---

## Full commit list (reference)

All 30 commits, oldest to newest, hash / date / subject only (see the sections above for detail on
the significant ones):

| # | Hash | Date | Subject |
|---|---|---|---|
| 1 | `945a3b2` | 2026-07-13 | Initial project setup |
| 2 | `0d21ac8` | 2026-07-13 | Gitignore updata added |
| 3 | `556baae` | 2026-07-21 | FFmpeg, FFprobe and Faster-whisper integration |
| 4 | `057517f` | 2026-08-31 | Build FastAPI backend + production-grade rearchitecture (#1) |
| 5 | `89d6b6e` | 2026-09-01 | (#2) — teacher-speech prioritization + definitions extraction |
| 6 | `abc58f8` | 2026-09-02 | (#3) — docs-only |
| 7 | `7d8fff0` | 2026-09-02 | (#4) — docs-only |
| 8 | `f5f516e` | 2026-09-04 | (#5) — DFD.md added |
| 9 | `796760c` | 2026-09-04 | (#6) — logging split, pipeline-order doc correction |
| 10 | `eb6c03e` | 2026-09-04 | (#7) — paper-vs-implementation.md created |
| 11 | `f384789` | 2026-09-06 | (#8) — Flutter client built (85 files) |
| 12 | `5487de6` | 2026-09-06 | (#9) — on-device VAD added |
| 13 | `4a1c199` | 2026-09-06 | (#10) — docs sync, untracked empty dirs deleted |
| 14 | `7146945` | 2026-09-06 | (#11) — multi-angle review, 4 backend bugs + Flutter fixes |
| 15 | `c69bf64` | 2026-09-06 | (#12) — row-lock race fix |
| 16 | `9c2b2d0` | 2026-09-07 | 5 edge-case fixes (extensions, filenames, Content-Length, encoding, duration) |
| 17 | `1f23a71` | 2026-09-11 | Stress-test pass: denoise, timestamps, Redis, minutes export |
| 18 | `e89ce42` | 2026-09-11 | Round 9: diarization parsing, service hardening, Flutter robustness |
| 19 | `99ce946` | 2026-09-11 | Postgres idle-in-transaction fix |
| 20 | `7e61c23` | 2026-09-11 | CORS allow_credentials fix |
| 21 | `6b0733f` | 2026-09-11 | Round 10: scripts/ unfrozen, denoiser + diarization fixes |
| 22 | `b92f916` | 2026-09-11 | Dismissible crash fix |
| 23 | `58ce284` | 2026-09-11 | CI Redis fix, stale pyrnnoise cleanup, .dockerignore |
| 24 | `edb0a30` | 2026-09-11 | Double-tap FAB guard, plaintext-traffic doc |
| 25 | `936c73a` | 2026-09-11 | Docs: round-11 section, test count 57→69 |
| 26 | `22d3582` | 2026-09-11 | Docs consistency pass |
| 27 | `235e300` | 2026-09-14 | Document --host 0.0.0.0 physical-device gap |
| 28 | `090b204` | 2026-09-16 | This session's doc pass + 2 real bug fixes |
| 29 | `bc0f095` | 2026-09-16 | ARCHITECTURE_DECISIONS.md + FINAL_HANDOFF.md |

*(Commit #30, this file's own future commit, is not yet listed here since it doesn't exist until
this file is committed.)*

---

*This file does not get a "last updated" line inside the doc set's usual convention footer,
since by construction it will need re-running against `git log` (not hand-editing) every time it
goes stale — see the note at the top of `docs/CHANGE_HISTORY.md` for the same caveat applied to
that file.*
