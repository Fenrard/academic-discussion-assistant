# Change History

> Written 2026-09-15 from `git log --oneline --reverse` (run directly this pass — 27 commits
> total, all listed below in order) and `docs/DevelopmentLog.md` (Nathan's own day-by-day journal).
> Nothing below is fabricated — every commit message is quoted verbatim from git's own history.

## Nathan's own early journal (`docs/DevelopmentLog.md`) — predates most of the git history below

A five-entry, informal day-by-day log, stopping abruptly:

> Day 1: Set up GitHub. Day 2: first steps with `record_test_audio.py`. Day 3: added
> `preprocess_audio.py`, integrated faster-whisper "on surface level for MVP completion." Day 4:
> reviewing `preprocess_audio.py`/`transcribe_audio.py` to close a comprehension gap, noting time
> pressure. Day 5: (empty — the log was not continued past this point).

`tester_terminal.txt` (a scratch file of manual CLI test commands for exactly these same four early
scripts) corroborates this era — and its old file paths show the project once lived under
`OneDrive\Documents\Thesis\...` before moving to its current location.

## Full commit history (oldest → newest)

**Era 1 — initial scripts (pre-#1, no PR numbers yet):**
```
945a3b2  Initial project setup
0d21ac8  Gitignore updata added
556baae  FFmpeg, FFprobe and Faster-whisper integration
```
This is the "six built scripts" foundation `CLAUDE.md` Part 2 describes — the standalone
`scripts/*.py` CLI tools, before any FastAPI backend existed.

**Era 2 — the backend gets built, then immediately re-architected for production concerns (#1):**
```
057517f  Build FastAPI backend + production-grade rearchitecture (#1)
```
One large commit/PR — per `CLAUDE.md` Part 2's "Production Architecture (Round 3)" section, this is
where the API/worker split, JWT auth, Postgres/Alembic, rate limiting, and Docker/CI all landed
together, in response to a discovered blocking-event-loop bug.

**Era 3 — closing feature gaps against the thesis's specific objectives (#2–#4):**
```
89d6b6e  Implement teacher-speech prioritization + definitions extraction (#2)
abc58f8  Document local infra + smoke tests in CLAUDE.md's Development Environment (#3)
7d8fff0  Replace stale 14-day sprint list with the actual current status (#4)
```

**Era 4 — diagrams and manuscript-vs-code reconciliation (#5–#7):**
```
f5f516e  Add DFD Level 0 and Level 1 diagrams (#5)
796760c  Verification pass: fix a real worker-tier logging bug + doc accuracy (#6)
eb6c03e  Compare thesis manuscript (Ch. 1 & 3) against the built system (#7)
```
`docs/DFD.md` (added here) explicitly notes it predates the Flutter client — worth remembering it's
a snapshot of the backend-only era, not the current full system. `docs/paper-vs-implementation.md`
(added here) is the manuscript-vs-code discrepancy tracker referenced throughout this documentation
set.

**Era 5 — the Flutter client gets built (#8–#11):**
```
f384789  Build the Flutter client — all six screens, verified end-to-end (#8)
5487de6  Add on-device VAD pre-filter, closing the hybrid-architecture gap (#9)
4a1c199  Bring CLAUDE.md and README.md fully current with the Flutter/VAD work (#10)
7146945  Multi-angle code review pass: fix real bugs found in Flutter + backend (#11)
```
This is the single biggest jump in the project's scope — before #8, there was no client at all
beyond `scripts/v2_smoke_test.py`/`ws_smoke_test.py` exercising the API directly.

**Era 6 — a real concurrency bug, then an extended bug-hunting/hardening arc (#12 onward, PR
numbering stops here — later commits use "round N" language instead, matching `CLAUDE.md` Part 2's
own "Resolved this pass, round N" sections):**
```
c69bf64  Fix the chunk_results lost-update race under a real multi-worker pool (#12)
9c2b2d0  Fix five real edge cases in the real-audio-ingestion path
1f23a71  Stress-test pass: fix denoise, streaming timestamps, Redis, minutes export
e89ce42  Round 9 bug-hunt: diarization output parsing, service hardening, Flutter robustness
99ce946  Don't hold a Postgres connection idle-in-transaction for the whole WS recording
7e61c23  CORS: allow_credentials False (Bearer-token auth, no cookies)
6b0733f  Round 10: fix scripts/ now that they're no longer frozen (PM call)
b92f916  Fix a real crash: failed swipe-delete poisons the session list on reload
58ce284  Infra cleanup: CI Redis URLs to 127.0.0.1, stale pyrnnoise/RNNoise mentions
edb0a30  Guard the New-session FAB against a double-tap; document plaintext traffic
```
This is where the RNNoise → `pyrnnoise` → FFmpeg `afftdn` denoiser switch happened (the
"Stress-test pass" commit), the diarization output-parsing crash was fixed (`e89ce42`), and the
"scripts are frozen" rule (an earlier project convention that the six original CLI scripts
shouldn't be touched once their logic was promoted into `backend/services/`) was explicitly lifted
by the project owner (`6b0733f`).

**Era 7 — documentation consistency passes (most recent):**
```
936c73a  Docs: add missing round 11 section, fix stale Flutter test count (57->69)
22d3582  Docs consistency pass: fix real contradictions between CLAUDE.md and README.md
235e300  Document the loopback-only uvicorn default that would've blocked a physical device
```

## Major architectural changes, in one list

1. **Standalone scripts → a real client/server backend** (Era 2) — the single largest structural
   change: introduced FastAPI, the database, auth, and the entire API surface at once.
2. **Synchronous single-process pipeline → API/worker split via Celery** (also Era 2, same commit)
   — fixed a real blocking-event-loop bug; this is the architectural fact everything in
   `docs/ARCHITECTURE.md` is built around.
3. **No client → the full Flutter app** (Era 5) — six screens, WebSocket streaming, on-device VAD.
4. **RNNoise (`pyrnnoise`) → FFmpeg `afftdn`** (Era 6) — an abandoned dependency, replaced after it
   became permanently uninstallable alongside this project's other requirements. See
   `docs/paper-vs-implementation.md` §3.3 and `docs/TROUBLESHOOTING.md`.
5. **"Scripts are frozen" → scripts actively maintained again** (Era 6, `6b0733f`) — an explicit,
   documented project-owner decision to reverse an earlier convention.

## Abandoned approaches (found, not fabricated)

- **RNNoise via `pyrnnoise`** — genuinely implemented, genuinely shipped for a time, then removed
  after `pyrnnoise` 0.4.3 became irreconcilable with this project's other pinned dependencies on
  Python 3.11 (a `ResolutionImpossible` pip conflict with `faster-whisper`'s `av` requirement).
  Zero references to it remain in `requirements.txt`/`requirements-api.txt`/`requirements-worker.txt`
  as of this pass (confirmed via direct grep).
- **"Scripts are frozen" as a development rule** — enforced for a time (logic was promoted into
  `backend/services/`, and the original `scripts/*.py` were meant to be left untouched afterward),
  then explicitly reversed by the project owner in commit `6b0733f` once real bugs were found in
  the scripts themselves.

## Current implementation vs. what came before

The most important throughline across this entire history: **the thesis manuscript's own described
architecture, pseudocode, and pipeline ordering do not always match what the code above actually
does** — and this is tracked deliberately, not accidentally, in `docs/paper-vs-implementation.md`,
added in Era 4 and referenced throughout `CLAUDE.md` Part 2. The most significant specific
divergence: the manuscript's pseudocode/DFD describes teacher identification running *before*
transcription; the actual, currently-running code runs it *after* transcription (teacher
verification slices audio by Whisper's own segment boundaries, which have to exist first). See
`docs/ARCHITECTURE.md`'s pipeline diagram for the real, current order.
