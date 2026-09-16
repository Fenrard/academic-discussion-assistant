# Architecture Decision Extraction

> Written 2026-09-17 by inspecting the repository's current code, every code comment/docstring
> that states a reason, `CLAUDE.md`'s full development record (Parts 1–3), `docs/paper-vs-
> implementation.md`, `docs/CHANGE_HISTORY.md`, the full `git log` (including commit message
> *bodies*, not just subjects), and the thesis manuscript's Chapter 3 (present in the repo
> directory, though not git-tracked). **No reasoning below is invented.** Where this project's own
> records state a reason, it is quoted or closely paraphrased with its source named. Where no
> reason could be found anywhere in the repository or its history, this document says so exactly:
>
> **"RATIONALE UNKNOWN — implementation exists but historical reasoning was not preserved."**
>
> A partial case appears too: some decisions have a documented *what* and a partial *why*, without
> a recorded comparison against alternatives. Those are marked explicitly as partial, not folded
> into either "fully documented" or "unknown."
>
> Companion reading: `docs/ARCHITECTURE.md` (how the current system works), `docs/CHANGE_HISTORY.md`
> (the commit-by-commit timeline these decisions emerged from), `docs/paper-vs-implementation.md`
> (specifically tracks manuscript-vs-code disagreements, several of which are decisions in their
> own right).

---

## 1. Flutter vs. Backend Responsibilities (thin client, thick server)

- **What was chosen:** A Flutter client that only captures audio, does a cheap on-device energy
  check, streams bytes over a WebSocket, and renders results — it runs zero ML inference. Every
  model (denoise, VAD, Whisper, diarization, speaker verification) runs server-side.
- **Alternatives considered:** `CLAUDE.md`'s "Hybrid Edge/Server Design" section explicitly frames
  the alternative as a spectrum, not a binary: "If local pipeline too slow: push diarization/
  verification to server path, keep VAD+denoise local." The document records that on-device
  denoise and a learned (not energy-heuristic) VAD were *considered* as future migrations, not
  adopted now.
- **Why the current approach was chosen:** Partially documented. `CLAUDE.md` states the on-device
  VAD gate exists "at effectively zero CPU/battery cost" (`local_vad.dart`'s own doc comment) and
  that on-device noise suppression was **deliberately not attempted**: *"real DSP noise suppression
  can't be safely validated without real audio and a human listening pass; shipping an untested
  half-measure risked silently degrading real speech, which was judged worse than leaving it open
  and documented"* (`CLAUDE.md`, "Hybrid Edge/Server Design"). The broader "why keep Whisper/
  diarization/verification server-side at all" question is answered by the Redmi Note 13 feasibility
  reasoning that also lives in this project's own history (measured RTF ≈2.4–2.9 on an 8-core desktop
  CPU makes a phone-class CPU an even worse fit, and shrinking Whisper to fit a phone would undercut
  the accuracy case the whole thesis is built on) — this reasoning appears in the "Scaitale Runbook"
  artifact produced during this project's own work, not as a git-tracked file, so it is *this
  project's own documented reasoning*, just not committed to source control.
- **What problem it solves:** Keeps the phone app simple and portable (no native ML runtime, no
  model bundling, no per-device performance variance) and keeps every model in one place to load
  once and reuse.
- **What tradeoffs it introduces:** Full dependency on network connectivity to the backend — there
  is no offline mode (see decision §26, "Graceful degradation when offline," listed as explicitly
  NOT built). Every chunk's round trip pays real network latency on top of processing latency.
- **What would break if replaced:** Moving Whisper on-device would require re-solving model
  distribution, a mobile inference runtime, and would very likely regress accuracy (a smaller model
  would be needed) — directly working against the thesis's low-resource-language accuracy objective.
- **Still appropriate?** Yes, given the measured performance numbers (`docs/ML_PIPELINE.md`) and the
  explicit accuracy-first framing above. The one upgrade this project's own analysis already
  recommends and hasn't done: moving the *client-side gate* from a plain energy heuristic to a real
  on-device Silero VAD model — cheap on this hardware tier, and closes the last open item in
  "Hybrid Edge/Server Design."
- **Files/functions:** `android/lib/screens/recording/live_recording_screen.dart`,
  `android/lib/core/local_vad.dart`, `android/lib/core/pcm_chunker.dart`,
  `backend/services/audio_service.py: run_pipeline()`.

## 2. Backend Web Framework — FastAPI

- **What was chosen:** FastAPI, not Flask, Django, or any other Python web framework.
- **Alternatives considered:** **RATIONALE UNKNOWN — implementation exists but historical reasoning
  was not preserved.** The very first commit (`945a3b2`, "Initial project setup") is a 15-line
  README with no framework discussion; FastAPI appears already chosen by the time any recorded
  reasoning begins. `CLAUDE.md`'s "Tech Stack (Final, Locked)" table states it as a locked fact, not
  a compared decision.
- **Why the current approach was chosen:** Not recorded. What *is* recorded is why the framework's
  own capabilities were later leaned on: native `async def` route support and first-class
  WebSocket support were both load-bearing for later decisions (§3, §4) — but that's a consequence
  of already having FastAPI, not a stated reason for picking it originally.
- **What problem it solves:** A modern, async-native Python API framework with automatic OpenAPI
  docs (`/docs`, confirmed working this session) and native WebSocket support without an add-on.
- **What tradeoffs it introduces:** None specifically attributable to this choice over alternatives,
  since no comparison was recorded.
- **What would break if replaced:** Every route decorator, `Depends()` injection
  (`backend/api/deps.py`), and the WS route's raw `WebSocket` object handling
  (`backend/api/transcribe.py`) are FastAPI-specific APIs — a framework swap would be a full rewrite
  of `backend/api/` and `backend/main.py`.
- **Still appropriate?** Yes — nothing in this project's actual usage pattern (async I/O-bound API
  tier, WebSocket streaming, Celery integration) argues against it, and it has caused no documented
  problems.
- **Files/functions:** `backend/main.py`, `backend/api/*.py`.

## 3. API/Worker Process Split via Celery

- **What was chosen:** Two separate OS processes — a FastAPI "API tier" that never runs ML code,
  and a Celery "worker tier" that does. Enforced and *proven*, not just intended: `requirements-
  api.txt`'s own header states it was "Verified via `import backend.api.transcribe; import
  backend.api.teacher` loading none of torch/faster_whisper/pyannote/silero_vad/speechbrain" — and
  this session independently reproduced that same check.
- **Alternatives considered:** The commit that introduced this (`057517f`, full body quoted in
  `docs/CHANGE_HISTORY.md`) describes the *prior* state as the alternative being replaced: `async
  def` routes calling the pipeline inline. Running pipeline code in a thread pool
  (`run_in_executor`) rather than a separate process, or using a different task queue (RQ, Dramatiq)
  instead of Celery, are not mentioned anywhere as having been considered.
- **Why the current approach was chosen:** Directly documented: *"Fixed a real blocking-event-loop
  bug: API routes ran CPU-bound pipeline code inline. Split into an API tier ... and a worker tier
  ... — verified the split is real by checking `sys.modules` after importing the API routers, and
  by running a genuinely separate worker process against real Postgres+Redis (not just eager
  mode)"* (commit `057517f` body). This was a **measured bug**, not a hypothetical: `CLAUDE.md`
  states the blocking behavior showed up as "measured RTF > 1, a live bug, not hypothetical."
- **What problem it solves:** A slow Whisper/diarization call no longer blocks the single-threaded
  asyncio event loop that serves every other request (including an unrelated `/health` check).
- **What tradeoffs it introduces:** Real operational complexity — two processes to run and monitor,
  a message broker (Redis) as a new failure mode, and out-of-order chunk completion to reason about
  (§27). The eager-mode fallback (§25) exists specifically to keep local dev/CI simple despite this.
- **What would break if reverted:** Every ML call would again run inline in the API process,
  reintroducing the exact blocking bug this split fixed — confirmed still true, since `backend/
  worker/tasks.py` deliberately keeps `audio_service`'s import lazy specifically so importing it
  from the API process (for `.delay()`) stays cheap; removing the split would make that laziness
  moot and the import cost (and blocking risk) would land back in the API process.
- **Still appropriate?** Yes — this is the single most load-bearing architectural decision in the
  backend, still correct under the current implementation, and actively re-verified this session
  (`import backend.main` pulls in zero ML libraries, confirmed by direct execution).
- **Files/functions:** `backend/main.py`, `backend/worker/celery_app.py`, `backend/worker/tasks.py`,
  `requirements-api.txt` vs. `requirements-worker.txt`.

## 4. WebSocket Transport (not HTTP polling)

- **What was chosen:** `WS /api/v1/ws/transcribe` as the live-streaming transport, locked from the
  project's earliest tech-stack table: *"WebSocket transport from day one — not HTTP POST with
  polling"* (`CLAUDE.md`, "Key Architectural Rules" #5).
- **Alternatives considered:** HTTP POST with polling is explicitly named as the rejected
  alternative in the rule's own wording — but no comparison of *why* polling was rejected is
  recorded beyond the rule's existence.
- **Why the current approach was chosen:** **RATIONALE UNKNOWN — implementation exists but
  historical reasoning was not preserved**, for the *original* choice. It predates any recorded
  reasoning the same way the FastAPI choice does. What can be said with confidence from the current
  implementation: WebSocket is what makes near-real-time chunk-by-chunk results possible at all
  (`docs/ARCHITECTURE.md`'s data-flow trace) — polling would need a client-driven interval, adding
  latency and wasted requests during silence.
- **What problem it solves:** Bidirectional, low-overhead delivery of `chunk_result` messages as
  each chunk finishes, without the client guessing how often to poll.
- **What tradeoffs it introduces:** WebSocket auth can't use a header (browsers/Flutter's WS client
  can't set one on the handshake) — forced the `?token=` query-param auth pattern (§33), a real,
  documented consequence of this choice, not a separate independent decision.
- **What would break if replaced:** The whole streaming UX (`live_recording_screen.dart`'s growing
  transcript) would need to become poll-driven, and the "session_ended" one-shot final payload
  pattern would need a new "is it done yet" endpoint.
- **Still appropriate?** Yes for the streaming case. `POST /transcribe` (whole-file) deliberately
  uses HTTP + polling instead (`android/lib/core/polling.dart: pollUntil()`) — proving the two
  transports coexist by design for their respective use cases, not that WebSocket was a mistake.
- **Files/functions:** `backend/api/transcribe.py: transcribe_stream()`,
  `android/lib/core/ws_transcribe_client.dart`.

## 5. Audio Recording — the `record` Package, Dual Capture Modes

- **What was chosen:** The Flutter `record` package (`^7.1.1`), used in **two different modes**:
  `startStream()` (headerless PCM16, live recording) and `start(path: ...)` (a real WAV file,
  teacher enrollment).
- **Alternatives considered:** **RATIONALE UNKNOWN** for why `record` specifically over other
  Flutter audio-capture packages (`flutter_sound`, `just_audio` + a recorder plugin, etc.) — no
  comparison recorded anywhere.
- **Why the current approach was chosen (for the dual-mode split specifically, which *is*
  documented):** Streaming mode is used for live recording because the WS contract needs
  chunk-by-chunk delivery; file mode is used for enrollment because it's a single short one-shot
  upload with no latency pressure (`android/lib/screens/enrollment/teacher_enrollment_screen.dart`
  uses `AudioRecorder.start(path: ...)` directly, per this session's own file read).
- **What problem it solves:** Matches capture mode to the actual latency requirement of each screen
  rather than forcing one uniform capture strategy.
- **What tradeoffs it introduces:** Two different code paths to maintain for "record audio," with
  different failure/permission-handling needs each (both handled — see `docs/FRONTEND.md`).
- **What would break if replaced:** `startStream()`'s headerless-PCM output is exactly why
  `wav_encoder.dart` exists at all (§6) — swapping capture packages could change output format
  assumptions throughout `pcm_chunker.dart`.
- **Still appropriate?** Yes — both modes work as intended, confirmed via this project's own
  on-device verification runs (`CLAUDE.md`, "Flutter Client (Built)").
- **Files/functions:** `android/lib/screens/recording/live_recording_screen.dart`,
  `android/lib/screens/enrollment/teacher_enrollment_screen.dart`, `android/pubspec.yaml`.

## 6. Audio Chunking — Fixed-Duration, Client-Wrapped WAV

- **What was chosen:** The client buffers raw PCM into fixed-duration blocks
  (`chunk_duration_seconds`, 1–10s bounded) and wraps each in a self-contained WAV header before
  sending, rather than streaming a continuous raw PCM socket the server reassembles.
- **Alternatives considered:** Not explicitly recorded as a comparison, but the reasoning for *why
  WAV-wrapping is needed at all* is directly stated: `record`'s `startStream()` "only emits
  headerless PCM16" and "the WS contract needs each binary frame to be a complete WAV file FFmpeg
  can parse" (`CLAUDE.md`, "Flutter Client (Built)"; `pcm_chunker.dart`'s own doc comment).
- **Why the current approach was chosen:** Chunking itself (as opposed to one continuous stream)
  is what makes near-real-time delivery possible — each chunk becomes an independently processable
  unit the worker tier can pick up as soon as it arrives, rather than waiting for the whole
  recording to end.
- **What problem it solves:** Lets transcription begin seconds into a recording instead of only
  after it stops, without needing a stateful, order-sensitive audio-reassembly protocol server-side.
- **What tradeoffs it introduces:** Each chunk is standardized/transcribed independently — no
  cross-chunk audio continuity at the FFmpeg/Whisper level (a real, documented limitation:
  "Per-chunk diarization has no cross-chunk speaker continuity," `CLAUDE.md`, "Known Open Issues").
  A `MIN_CHUNK_DURATION_SECONDS` floor exists specifically because a too-short trailing chunk
  reliably triggered a Whisper repetition-loop hallucination (`CLAUDE.md`, round 10) — a concrete,
  measured failure mode that shaped this exact constant's existence.
- **What would break if replaced:** Removing the WAV wrapper would break every FFmpeg call
  server-side, which expects a parseable container per chunk, not a raw PCM blob.
- **Still appropriate?** Yes, with the caveat already on record: this project's own measured RTF
  (≈2.4–2.9) means chunking alone doesn't achieve true real-time transcription — the chunking
  design is sound, the model speed is the actual bottleneck (§13/§14 territory, not this decision).
- **Files/functions:** `android/lib/core/pcm_chunker.dart`, `android/lib/core/wav_encoder.dart`,
  `backend/core/config.py: min_chunk_duration_seconds/max_chunk_duration_seconds`,
  `backend/schemas/pipeline.py: PipelineOptions.chunk_duration_seconds`.

## 7. On-Device Pre-Filter VAD — a Plain Energy Heuristic, Not a Model

- **What was chosen:** `android/lib/core/local_vad.dart` — windowed RMS energy check, explicitly
  **not** a machine-learning model (no bundled Silero/WebRTC VAD on-device).
- **Alternatives considered:** Explicitly named and rejected in the file's own doc comment: *"This
  is deliberately not a learned model (no Silero/WebRTC VAD bundled) — a simple energy gate is
  enough to decide 'does this chunk plausibly contain speech' before it ever leaves the phone, at
  effectively zero CPU/battery cost and no native dependency."*
- **Why the current approach was chosen:** Directly stated in the quote above — cost/complexity
  outweighs the accuracy benefit of a learned model for a binary send/don't-send gate. Also
  documented: windowing (sub-frame RMS, not one whole-buffer average) was a deliberate strengthening
  found during this feature's own design review, specifically to avoid a short utterance inside an
  otherwise-quiet chunk reading as silence.
- **What problem it solves:** Reduces wasted bandwidth/battery sending silent chunks, at effectively
  zero cost, while the "unmeasured until real data exists" threshold caveat (same class as
  `teacher_verification_threshold`) is explicitly carried in the same comment.
- **What tradeoffs it introduces:** A fixed `-40 dBFS`-ish default threshold, "unvalidated... not
  calibrated against real classroom audio" (own doc comment) — real classroom noise floors could
  make this too aggressive or too lax; nobody has measured which.
- **What would break if replaced:** A learned on-device VAD would need a bundled model + an ONNX
  Runtime Mobile (or similar) dependency — the exact upgrade this project's own hybrid-design
  analysis recommends as the next worthwhile step (§1).
- **Still appropriate?** Yes for now — 9 dedicated unit tests plus a real on-device silent-mic run
  both confirm it behaves correctly even in the adversarial all-silence case
  (`CLAUDE.md`, round 5).
- **Files/functions:** `android/lib/core/local_vad.dart`, `android/lib/core/pcm_chunker.dart`.

## 8. FFmpeg Preprocessing — Always On, Never Toggleable

- **What was chosen:** Every audio unit (chunk, whole-file upload, enrollment sample) is
  standardized (16kHz mono PCM WAV + loudnorm) via FFmpeg, unconditionally — locked as "Key
  Architectural Rule #1" in `CLAUDE.md`: *"FFmpeg preprocessing is ALWAYS ON — never toggleable."*
- **Alternatives considered:** Not documented as a comparison — this appears to be a foundational,
  pre-recorded-history rule (present since before the earliest git commits with detailed reasoning).
- **Why the current approach was chosen:** Not explicitly justified in any single place, but the
  *consequences* of skipping it were caught and documented as real bugs: teacher enrollment audio
  once skipped this step and failed with *"an opaque 'Expected 16000Hz, got Xhz' error on anything
  not already exactly 16kHz mono WAV"* (`CLAUDE.md`, round 5) — direct evidence for why the rule is
  enforced everywhere, even if the original motivation for the rule itself predates recorded
  reasoning.
- **What problem it solves:** Guarantees every downstream model (Silero, Whisper, SpeechBrain) sees
  exactly the sample rate/channel layout it expects, regardless of upstream format variance (phone
  codecs, browser codecs, different recording apps).
- **What tradeoffs it introduces:** A fixed per-chunk FFmpeg subprocess cost (~0.26s measured,
  `CLAUDE.md` round 8) on every single chunk, even already-compliant ones.
- **What would break if replaced:** Removing this would reopen the exact "Expected 16000Hz" class of
  crash the round-5 fix closed, and would let a phone-recorder format (`.3gp`, `.amr`, etc.) reach
  Whisper without ever being decoded into a shape it accepts.
- **Still appropriate?** Yes — no documented downside outweighs the correctness guarantee, and its
  cost is small relative to Whisper's own per-chunk time.
- **Files/functions:** `backend/services/audio_service.py: ingest_audio()`,
  `scripts/preprocess_audio.py: preprocess_audio()`.

## 9. Noise Suppression — FFmpeg `afftdn`, Replacing RNNoise/`pyrnnoise`

- **What was chosen:** FFmpeg's built-in `afftdn` (FFT-based adaptive denoise) filter, `nr=12:nf=
  -25:tn=1`, applied in place at 16kHz.
- **Alternatives considered — extensively documented, the best-recorded decision in this whole
  project:** Three real stages, per `docs/paper-vs-implementation.md` §3.3: (1) the thesis
  manuscript's own original plan named RNNoise specifically, "applied through FFmpeg's `arnndn`
  filter"; (2) the actual first implementation used the `pyrnnoise` Python library instead, "chosen
  for portability (a plain `pip install`, no external `.rnnn` model file to manage)" — a **recorded,
  deliberate deviation** from the manuscript's own plan; (3) `afftdn`, the current choice.
- **Why the current approach was chosen:** Directly and thoroughly documented. `pyrnnoise` 0.4.3
  (its last release) became **permanently uninstallable** alongside this project's other
  dependencies: *"incompatible with every `audiolab`/PyAV combination that still installs on Python
  3.11 (the required PyAV downgrade is `ResolutionImpossible` against `faster-whisper`)"*
  (`docs/paper-vs-implementation.md` §3.3). On top of that, it had **zero test coverage**, so the
  break "sat unnoticed until a full-pipeline stress test with `enable_denoise=True`"
  (`CLAUDE.md`, round 8) — and its own cleanup path made things worse: a raw `.unlink()` on a file
  `audiolab` still had open threw `PermissionError [WinError 32]`, which *replaced* the real
  exception in the traceback and leaked a temp file permanently. `afftdn` was chosen specifically
  for "zero-setup portability" (no external model file, unlike the `arnndn` fallback that would
  need a committed `.rnnn` file) — a PM decision, explicitly attributed as such in both
  `docs/paper-vs-implementation.md` and `CLAUDE.md`.
- **What problem it solves:** In-place denoising at 16kHz with no resample round-trip, no Python
  dependency beyond FFmpeg itself, ~0.1s/chunk (vs. the old pipeline's three-FFmpeg-subprocess
  round-trip cost).
- **What tradeoffs it introduces:** `afftdn` is classical FFT-domain spectral subtraction, not a
  neural denoiser — its `nr`/`nf`/`tn` parameters are an *"unvalidated heuristic starting point,
  same caveat as `teacher_verification_threshold`"* (`audio_service.py`'s own code comment),
  meaning real classroom noise conditions have never been used to tune it. RNNoise (the manuscript's
  original named technique) is a genuinely different, learned approach — swapping filters is a real,
  disclosed deviation from what the manuscript describes, not a drop-in equivalent.
- **What would break if replaced:** Reverting to `pyrnnoise` would immediately reintroduce the
  `ResolutionImpossible` dependency conflict — this isn't a stylistic reversal, it's currently
  impossible to install alongside `faster-whisper` on Python 3.11 without also downgrading `av`.
- **Still appropriate?** Yes, pragmatically — but explicitly *unvalidated*, by its own code comment.
  The honest open item is real: nobody has run a before/after listening test against actual noisy
  classroom audio to confirm `afftdn`'s parameters are well-tuned, or that FFT-domain denoising is
  even the right general approach compared to a modern neural denoiser that *does* install cleanly
  (this project has not evaluated any denoiser besides these two).
- **Files/functions:** `backend/services/audio_service.py: clean_audio()`, `DENOISE_FILTER`
  constant; `scripts/process_pipeline.py`; `tests/test_audio_denoise.py`.

## 10. Voice Activity Detection (Server-Side) — Silero VAD

- **What was chosen:** Silero VAD (`silero-vad` package) for server-side speech-span segmentation.
- **Alternatives considered:** **RATIONALE UNKNOWN — implementation exists but historical reasoning
  was not preserved.** No comparison against WebRTC VAD, py-webrtcvad, or any other VAD library
  appears anywhere in the codebase, `CLAUDE.md`, or git history. It is locked in the tech-stack
  table from the start of recorded history.
- **Why the current approach was chosen:** Not recorded for the *model* choice itself. What *is*
  recorded is a specific implementation workaround forced by this choice: Silero's own `read_audio()`
  helper pulls in torchaudio's `torchcodec` backend, which conflicts with this project's FFmpeg
  setup on Windows — worked around by using `soundfile.read()` instead
  (`backend/services/audio_service.py: load_waveform()`'s own comment, and independently reproduced
  this session as a real, non-fatal warning during a live `pytest` run).
- **What problem it solves:** Finds precise speech-span boundaries within already-standardized audio
  so Whisper doesn't waste time transcribing silence/noise.
- **What tradeoffs it introduces:** A second, real Windows-specific dependency conflict
  (torchcodec/FFmpeg DLL loading) that required its own workaround — a maintenance cost directly
  attributable to this library choice on this platform.
- **What would break if replaced:** `detect_speech()`'s whole contract (returning `{start_sample,
  end_sample, start_seconds, end_seconds}` spans) would need to be re-implemented against a new
  library's own output format; `transcribe_audio()` iterates these spans directly.
- **Still appropriate?** Functionally yes — it works, is fast (a 2.8× speedup was measured just from
  loading it once instead of per-call, `CLAUDE.md` round 5), and its Windows workaround is stable.
  Whether it's *better* than an alternative was never evaluated, so this can't be assessed either
  way beyond "it functions correctly."
- **Files/functions:** `backend/services/audio_service.py: detect_speech(), load_waveform()`,
  `backend/worker/celery_app.py: _load_models()`.

## 11. Speaker Verification Model — SpeechBrain ECAPA-TDNN

- **What was chosen:** `speechbrain/spkrec-ecapa-voxceleb`, used zero-shot (no fine-tuning), cosine
  similarity against enrolled embeddings.
- **Alternatives considered:** **RATIONALE UNKNOWN** for why this specific model/library over other
  speaker-embedding options (e.g., Resemblyzer, pyannote's own embedding model, a raw x-vector
  implementation) — locked in the tech-stack table with no recorded comparison.
- **Why the current approach was chosen:** Not recorded for the model choice. What *is* explicitly
  documented is the consequence of it being trained on VoxCeleb (a general-purpose,
  largely-English-interview-audio dataset) rather than this project's target population: *"its
  similarity threshold for identifying teacher speech is treated as an unvalidated default subject
  to evaluation"* (thesis manuscript, Script 1 pseudocode text — matching this session's own
  fact-check of `teacher_verification_threshold` in `backend/core/config.py`).
- **What problem it solves:** A compact, fixed-length embedding that lets a short enrollment sample
  be compared against a classroom speech segment via simple cosine similarity — no re-training
  needed per teacher.
- **What tradeoffs it introduces:** The VoxCeleb-trained embedding space has never been validated
  against Hiligaynon/Filipino/English speakers specifically or against real classroom acoustic
  conditions — the `0.35` threshold default is a literature-informed guess (near a "typical VoxCeleb
  EER operating point," `config.py`'s own comment), not a measured value for this project's actual
  population.
- **What would break if replaced:** `teacher_verification_service.py`'s `extract_embedding()`/
  `cosine_similarity()`/`verify_segment()` and the stored embedding shape in
  `TeacherEnrollment.embedding` (a JSON `list[float]`) are all shaped around whatever dimensionality
  this specific model produces (192-dim for ECAPA-TDNN's standard architecture) — a model swap would
  need re-enrollment of every existing teacher, since old and new embeddings would live in
  different, incompatible vector spaces.
- **Still appropriate?** Functionally yes (a synthetic functional check found clean separation
  between a real match, a pitch-shifted proxy, silence, and white noise — `CLAUDE.md` round 8), but
  the real-world accuracy claim central to the thesis's Objective 2/5 remains genuinely unverified
  against real enrolled-vs-unenrolled classroom data.
- **Files/functions:** `backend/services/teacher_verification_service.py`,
  `backend/models/teacher.py: TeacherEnrollment.embedding`,
  `backend/core/config.py: speaker_verification_model, teacher_verification_threshold`.

## 12. Speaker Diarization — pyannote.audio, Optional and Off by Default

- **What was chosen:** `pyannote/speaker-diarization-community-1`, gated behind a Hugging Face
  token, `enable_diarization` defaulting to `False`.
- **Alternatives considered:** The manuscript and `CLAUDE.md` both frame the real alternative
  explicitly: doing *no* diarization at all and relying solely on teacher/non-teacher classification
  — not a different diarization library. `CLAUDE.md`'s Scope/Limitation text states plainly: *"if
  diarization tools such as pyannote.audio cannot be integrated within project constraints, the
  system will still evaluate teacher speech identification using speaker embeddings and similarity
  matching"* — i.e., diarization was scoped as optional from the start, not chosen after comparing
  libraries.
- **Why the current approach was chosen:** Documented as a scope/cost decision, not a technical
  comparison: full diarization is *"treated as an optional enhancement rather than a guaranteed
  feature"* because it is *"the heaviest single stage in the pipeline"* (`CLAUDE.md`, "Explicitly
  Out of Scope") and because the thesis's actual objectives only require teacher/non-teacher
  classification, not full multi-speaker identity resolution — a distinction `docs/future_ideas.md`
  and `docs/paper-vs-implementation.md` both reason about explicitly (per-role/per-student
  identification was never a functional requirement).
- **What problem it solves:** Optionally labels generic "Speaker A/B/C" turns, when a deployment
  wants that extra detail and has an HF token configured.
- **What tradeoffs it introduces:** Requires a Hugging Face account, accepting a gated model's
  terms, and a real token — friction most deployments of this prototype will skip, by design.
  Untested this session specifically because no `HF_TOKEN` was configured in this environment.
- **What would break if replaced or removed entirely:** `merge_transcript_with_speakers()`'s
  time-overlap join and the `speaker_segments` field would disappear — but nothing else in the
  pipeline depends on diarization output; teacher verification is independently proven to work
  without it (§11), which is exactly the architectural property this decision was designed to
  preserve.
- **Still appropriate?** Yes — a real bug was found and fixed here (round 9: the community-1
  model's `DiarizeOutput.speaker_diarization` unpacking was wrong on every real run, `AttributeError`
  on every genuine call, invisible because it's off by default and untested without a real token),
  and the decision to keep it optional/decoupled is exactly what limited that bug's blast radius to
  a feature nobody was exercising yet.
- **Files/functions:** `backend/services/diarization_service.py`,
  `backend/services/audio_service.py: merge_transcript_with_speakers()`.

## 13. Transcription Engine — Faster-Whisper (not WhisperX, not vanilla `openai-whisper`)

- **What was chosen:** The `faster-whisper` package (CTranslate2-backed), model size `small`,
  `int8` quantization, CPU.
- **Alternatives considered:** WhisperX is **not present anywhere in this codebase** — grepped this
  session, zero references in any file, any requirements file, or any doc. Vanilla `openai-whisper`
  is likewise absent.
- **Why the current approach was chosen:** **RATIONALE UNKNOWN** for the specific comparison against
  WhisperX or vanilla Whisper — no such comparison is recorded anywhere. What can be inferred from
  the current implementation's own properties (labeled as inference, not fact): CTranslate2's `int8`
  CPU quantization directly serves this project's own "no GPU currently used" reality (§26) in a way
  vanilla Whisper's PyTorch-only inference path would not do as efficiently; WhisperX's main
  differentiators (forced alignment, built-in diarization) duplicate work this project already does
  its own way (Silero VAD, its own diarization integration) rather than filling a gap.
- **What problem it solves:** Multilingual speech-to-text — the core function of the entire app.
- **What tradeoffs it introduces:** Measured directly this project's own testing: streaming RTF
  ≈2.4–2.9 on an 8-core desktop CPU — slower than real-time (`CLAUDE.md`, round 8). This is the
  dominant cost in the entire pipeline by a wide margin over every other stage (`docs/
  ML_PIPELINE.md`).
- **What would break if replaced:** `load_whisper_model()`'s `WhisperModel(...)` constructor call
  and `transcribe_audio()`'s `.transcribe()` call are both `faster-whisper`'s own API surface;
  `WHISPER_MODEL_SIZE`'s "accepts a local CTranslate2 directory" behavior (used for the planned
  fine-tuned model, §16) is also CTranslate2-specific — a switch to WhisperX or vanilla Whisper
  would need a different model-loading/inference contract and a different fine-tune-to-runtime
  conversion path (`ai/finetuning/convert_to_faster_whisper.py` is literally named for this specific
  runtime).
- **Still appropriate?** Yes for a CPU-only deployment — the `WHISPER_CPU_THREADS` tuning knob
  (~17% measured improvement) is exactly the kind of lever CTranslate2 exposes that a
  PyTorch-native pipeline wouldn't as directly.
- **Files/functions:** `backend/services/audio_service.py: load_whisper_model(), transcribe_audio()`,
  `backend/core/config.py: whisper_model_size, whisper_device, whisper_compute_type,
  whisper_cpu_threads`.

## 14. Whisper Model Size — `small`, Not `tiny`/`base`/`medium`/`large`

- **What was chosen:** `small` as the default (`WHISPER_MODEL_SIZE`).
- **Alternatives considered:** `tiny`, `base`, `medium`, `large` — Whisper's own standard size
  ladder. This project's own hybrid-feasibility analysis (produced during this project's work, the
  "Scaitale Runbook") directly names `tiny`/`base` as the sizes that *would* fit a phone-class CPU
  near real-time, making the rejection explicit rather than merely implied.
- **Why the current approach was chosen:** Directly documented (same source): *"this project chose
  Whisper small over tiny/base deliberately, for accuracy on trilingual code-switched speech — the
  whole thesis question. Shrinking the model to fit a phone's CPU would directly undercut the
  accuracy case the fine-tuning work... exists to make."* This is a real, stated tradeoff
  acknowledgment, not an unexamined default.
- **What problem it solves:** Better baseline multilingual accuracy than `tiny`/`base`, without
  paying `medium`/`large`'s much heavier compute cost that this project's CPU-only deployment
  (§26) couldn't realistically absorb.
- **What tradeoffs it introduces:** Directly responsible for the RTF ≈2.4–2.9 slower-than-real-time
  result (§13) — a larger model would be slower still, a smaller one faster but measurably less
  accurate on exactly the code-switching task this thesis is about.
- **What would break if replaced:** Any change here is a pure runtime config value
  (`WHISPER_MODEL_SIZE`), so nothing "breaks" mechanically — but changing it silently trades away
  the accuracy rationale above without updating the thesis's own stated reasoning for the choice.
- **Still appropriate?** Yes, given the stated priority (accuracy over speed, for a low-resource
  language evaluation) — though this priority itself is a value judgment the thesis proposal makes,
  not something this document can independently validate.
- **Files/functions:** `backend/core/config.py: whisper_model_size` (default `"small"`).

## 15. Language Handling — No Forced Language, Per-Segment Auto-Detection

- **What was chosen:** `model.transcribe(clip, beam_size=beam_size)` — no `language=` argument
  passed, ever. Whisper auto-detects language independently for every VAD-detected segment.
- **Alternatives considered:** Forcing a single language for a whole session (or defaulting to
  English/Filipino) is the obvious alternative; not discussed anywhere in the codebase or history.
- **Why the current approach was chosen:** **RATIONALE UNKNOWN — implementation exists but
  historical reasoning was not preserved.** No code comment, commit, or doc explains this choice —
  grepped `audio_service.py` directly this session, found nothing. The clear technical *effect*
  (each segment can independently resolve to a different language, which is what code-switching
  requires) is self-evident from reading the code, but that is this document's own inference about
  *why it would matter*, not a recorded justification for choosing to build it this way.
- **What problem it solves (inferred from effect, not from a recorded statement of intent):** Lets
  a session move between Hiligaynon/Filipino/English across segments without one forced language
  tag suppressing whichever segments don't match it.
- **What tradeoffs it introduces:** The session-level `language`/`language_probability` fields are
  captured from only the **first** transcribed segment (`transcribe_audio()`'s own logic: `if
  detected_language is None: detected_language = info.language`) — an accepted, documented artifact
  (`CLAUDE.md`: "Whisper first-segment language lock on code-switched speech — known artifact,
  accepted") that means no per-segment language label is ever persisted, even though each segment's
  detection call is independent internally.
- **What would break if replaced:** Forcing a language would very likely suppress or garble
  transcription of any segment not in that language — directly working against the trilingual scope
  this project is built around.
- **Still appropriate?** Yes, and it's hard to construct an alternative that would serve this
  project's stated trilingual scope better — but the missing per-segment language field is a real,
  acknowledged gap if the thesis's language-broken-out WER analysis (Objective 5) needs it.
- **Files/functions:** `backend/services/audio_service.py: transcribe_audio()`.

## 16. Hiligaynon Adaptation — LoRA/PEFT, Not Full Fine-Tuning or From-Scratch Training

- **What was chosen:** Low-Rank Adaptation (LoRA) via the `peft` library, adapting `openai/
  whisper-small`'s weights, rather than full fine-tuning (updating every weight) or training a new
  model from scratch.
- **Alternatives considered:** Both alternatives are explicitly named and rejected in `CLAUDE.md`'s
  "Explicitly Out of Scope": *"Training ASR models from scratch"* is out of scope outright. Full
  fine-tuning isn't named as explicitly considered, but PEFT's own definition of terms entry in the
  thesis manuscript frames the choice as inherent to the technique category: *"parameter-efficient
  fine-tuning refers to techniques that adapt a large pretrained model to a new domain by training
  only a small set of additional parameters while keeping the original model weights frozen."*
- **Why the current approach was chosen:** Documented as a resource/feasibility decision:
  `CLAUDE.md`'s Scope section states the project *"will not train an automatic speech recognition
  model from scratch due to limitations in time, dataset availability, and computational
  resources."* LoRA specifically (over full fine-tuning) is the standard technique for adapting a
  model on a small dataset with limited compute (Google Colab's free GPU tier, also explicitly
  named as the training platform) — full fine-tuning of even a "small" Whisper model would need
  meaningfully more data and GPU memory than a free Colab tier reliably offers, though this specific
  comparative reasoning is this document's own inference, not something stated outright anywhere in
  the repo.
- **What problem it solves:** Lets a genuinely low-resource language (Hiligaynon, no dedicated
  Whisper token) be targeted without needing a large labeled corpus or expensive compute.
- **What tradeoffs it introduces:** LoRA adapts less of the model than full fine-tuning would —
  a real ceiling on how much the adaptation can shift Whisper's behavior, acknowledged implicitly by
  the project's own framing of fine-tuning as something to be *evaluated*, not assumed to succeed
  (thesis RQ3: "how accurately can the system transcribe... under low-resource language
  conditions").
- **What would break if replaced:** `ai/finetuning/finetune_whisper.py`'s training loop and
  `convert_to_faster_whisper.py`'s merge-then-convert step are both LoRA-specific (`convert_to_
  faster_whisper.py`'s own purpose is merging a LoRA adapter into base weights before CTranslate2
  conversion, since CTranslate2 can't load a bare adapter) — a full-fine-tuning approach wouldn't
  need the "merge" step at all, since there'd be no separate adapter to merge.
- **Still appropriate?** Cannot be assessed on results — **this has never been run.**
  `datasets/processed/` is empty (confirmed this session, `.gitkeep` only), no trained checkpoint
  exists anywhere in the repo or its gitignored `models/` folder. The scaffold is real, tested for
  import-time and error-path correctness, but the actual adaptation-quality question this decision
  exists to answer is entirely open.
- **Files/functions:** `ai/finetuning/finetune_whisper.py`, `ai/finetuning/
  convert_to_faster_whisper.py`, `backend/core/config.py: whisper_model_size` (the env var a trained
  adapter would eventually be pointed at).

## 17. Kinaray-a — Explicitly Considered and Excluded

- **What was chosen:** Trilingual scope only — Hiligaynon, Filipino, English. Kinaray-a (a related
  Panay language) is named and excluded.
- **Alternatives considered:** Including Kinaray-a as a fourth language is the explicit alternative
  named: `CLAUDE.md`'s "Explicitly Out of Scope" list states *"Kinaray-a — explicitly considered
  and cut; trilingual scope is final."*
- **Why the current approach was chosen:** The specific reasoning tying this decision to Kinaray-a
  by name is not elaborated beyond "trilingual scope is final." **INFERRED, not stated outright for
  Kinaray-a specifically:** this almost certainly ties to the same resource/timeframe constraints
  stated for the Hiligaynon corpus itself (`CLAUDE.md`'s Data Collection Tracking section discusses
  transcription effort as "the bottleneck, not GPU training") — a fourth language would multiply
  that same bottleneck. This linkage is this document's own reasonable inference, not a directly
  recorded justification.
- **What problem it solves:** Keeps the fine-tuning corpus, the glossary, and the evaluation set all
  bounded to three languages instead of an open-ended regional-language list.
- **What tradeoffs it introduces:** `CLAUDE.md`'s own "Language Scope (CRITICAL)" rule treats any
  reference to a fourth language anywhere in code/docs/comments as an outright error ("'Quadrilingual'
  anywhere... is an ERROR") — a strict, actively-enforced boundary, not just a soft preference.
- **What would break if replaced:** Every trilingual-specific artifact — the glossary's language
  coverage, the keyword service's trilingual stopword list, the minutes service's trilingual
  regex patterns for definitions/action-items — would need a fourth language's patterns added
  throughout, not just a single config flag.
- **Still appropriate?** Yes, and actively enforced — no code, comment, or doc found anywhere this
  session violates the trilingual boundary.
- **Files/functions:** `CLAUDE.md` "Language Scope (CRITICAL)"; trilingual patterns throughout
  `backend/services/keyword_service.py` (`_STOPWORDS`) and `backend/services/minutes_service.py`
  (`_ACTION_TRIGGERS`, `_DEFINITION_PATTERNS`).

## 18. Code-Switching Post-Processing — Glossary-Based Correction, Applied Per-Segment

- **What was chosen:** A hand-maintained JSON glossary (`backend/data/glossary.json`), applied via
  case-insensitive/case-preserving regex substitution immediately after each Whisper segment is
  decoded — not a second model pass, not a rule-based grammar corrector.
- **Alternatives considered:** Not recorded as an explicit comparison. The glossary's own `_meta`
  field frames it as a starting point meant to grow empirically: *"not derived from real Whisper
  error logs on the Hiligaynon classroom corpus yet. Grow this from actual transcription errors
  observed during the September fine-tuning data pass."*
- **Why the current approach was chosen:** A glossary substitution is the simplest possible fix for
  a known, narrow failure mode (Whisper phonetically misspelling specific recurring
  Hiligaynon/Filipino/English terms it has no dedicated vocabulary for) — cheaper than a second
  model pass and immediately auditable (every correction is a literal, inspectable
  `{"wrong": "right"}` entry). This reasoning is inferred from the mechanism's own simplicity and
  stated purpose, not from an explicit "we chose this over X" statement.
- **What problem it solves:** Corrects specific, recurring, predictable transcription errors
  (e.g., `"asaynment"` → `"assignment"`, `"ma'm"` → `"ma'am"`) without needing a general-purpose
  grammar/spelling model.
- **What tradeoffs it introduces:** Only fixes errors someone has already seen and added to the
  list — a genuinely novel misrecognition gets no correction. The glossary is presently a "starter/
  example list," not derived from real classroom error logs, by its own admission.
- **What would break if replaced:** `keyword_service.py`/`minutes_service.py` both consume
  already-corrected segment text; removing this stage would let uncorrected phonetic errors flow
  into keyword extraction and minutes generation, directly degrading both.
- **Still appropriate?** Yes as a placeholder mechanism, but its actual value is unproven — it
  cannot meaningfully help until it's grown from real transcription error logs, which don't exist
  yet (blocked on the same real-classroom-audio gap as fine-tuning itself).
- **Files/functions:** `backend/services/glossary_service.py: Glossary, load_glossary()`,
  `backend/data/glossary.json`.

## 19. Keyword Extraction — From-Scratch TextRank on NetworkX

- **What was chosen:** A hand-written implementation of classic TextRank (Mihalcea & Tarau, 2004) on
  top of `networkx`'s PageRank — not `nltk`/`sumy` (which bundle TextRank implementations), not an
  embedding-based or LLM-based keyword extractor.
- **Alternatives considered:** `nltk`/`sumy` are explicitly named and rejected in the module's own
  docstring: *"implemented from scratch on top of networkx (no nltk/sumy dependency — those pull in
  large corpora/heavy installs for what's a small, well-understood graph algorithm)."*
- **Why the current approach was chosen:** Directly documented in the quote above — a dependency-
  weight tradeoff, not an accuracy one. `nltk` in particular is known for large downloadable corpora
  even for basic tokenization use, which this project's own trilingual, code-switched text doesn't
  need in the first place (it uses its own hand-curated trilingual stopword list instead).
- **What problem it solves:** Domain-relevant keyword/keyphrase extraction with a small, auditable,
  dependency-light implementation this project fully controls (including the round-9 fix for
  `PowerIterationFailedConvergence`, which a black-box library dependency would have been harder to
  patch around).
- **What tradeoffs it introduces:** A hand-curated trilingual stopword list is *"best-effort, not a
  linguistically exhaustive resource"* (module docstring) — real gaps will surface as more
  code-switched transcripts are processed.
- **What would break if replaced:** `build_weighted_text()`'s teacher-weighting mechanism (repeating
  teacher-labeled text before extraction) is layered directly on top of this specific
  implementation's tokenize-then-graph pipeline — a swap to a black-box library's TextRank would
  need to find an equivalent injection point for that weighting.
- **Still appropriate?** Yes — it works, is tested, and required no dependency footprint most
  alternatives would have added.
- **Files/functions:** `backend/services/keyword_service.py: extract_keywords(),
  build_weighted_text()`.

## 20. Minutes Generation — Rule-Based Structuring, Not an LLM/Abstractive Summarizer

- **What was chosen:** Silence-gap topic segmentation, TextRank keywords, regex-pattern definitions
  and action-items — explicitly, by the module's own docstring, *"deliberately not an LLM/
  abstractive summarizer."*
- **Alternatives considered:** An LLM/abstractive summarizer is the named alternative, rejected
  outright by design. No specific LLM provider/API is named as having been evaluated and rejected.
- **Why the current approach was chosen:** Partially documented. The stated framing is scope-level:
  *"This is a heuristic, not an NLP model — it will miss/misfire on real classroom audio. Good
  enough for a functional prototype; not claimed to be more than that"* (`minutes_service.py`'s own
  docstring). This ties into two other, independently documented project-wide constraints that make
  a plausible (but not explicitly stated-as-the-reason) case: the project runs *"entirely within a
  local network, with no paid cloud services"* (thesis manuscript, Environment section, and
  `CLAUDE.md`'s original scope framing) — an LLM API call would violate that constraint directly.
  This specific causal link (no-cloud-services → no LLM) is **this document's own inference**, not
  a statement found anywhere connecting the two explicitly.
- **What problem it solves:** Deterministic, reproducible, zero-marginal-cost, zero-network-
  dependency structured output generation — the same input always produces the same minutes, useful
  for a thesis evaluation methodology that needs repeatable results.
- **What tradeoffs it introduces:** Definitions/action-items rely on pattern matching that will miss
  differently-phrased instances and can false-positive on superficially similar sentences — an
  explicit, acknowledged precision/recall tradeoff (`minutes_service.py`'s own comments on the
  English definition pattern requiring an article specifically to avoid over-triggering).
- **What would break if replaced:** The entire teacher-weighting mechanism (§21) and every
  regex pattern in `_ACTION_TRIGGERS`/`_DEFINITION_PATTERNS` would become moot — an LLM-based
  summarizer would need its own, different mechanism for teacher-prioritization (e.g., a
  system-prompt instruction) and wouldn't need trilingual regex patterns at all.
- **Still appropriate?** Defensible for a thesis prototype's stated scope, but genuinely unproven —
  precision/recall against real classroom audio is unmeasured (same "needs real data" gap as
  everywhere else in this project), and the module's own docstring is explicit that it "will miss/
  misfire on real classroom audio."
- **Files/functions:** `backend/services/minutes_service.py: generate_minutes()`.

## 21. Teacher Prioritization Mechanism — Weighting, Not a Separate Transcript

- **What was chosen:** A single transcript, with `is_teacher` metadata attached per segment;
  "prioritization" is applied downstream as a *weighting* effect (repeated text in the TextRank
  input, teacher-first sort in minutes key-point selection) rather than as a second, forked
  transcript object.
- **Alternatives considered:** A literal separate "teacher-prioritized transcript" is the
  alternative implied by the thesis manuscript's own earlier pseudocode language (Script 4's text,
  now corrected during this project's own documentation work to explicitly disclaim this: *"Rather
  than creating a separate teacher-prioritized transcript, the system applies teacher-based
  weighting during subsequent keyword extraction and summary generation"* — this exact sentence was
  added to the manuscript specifically to correct that impression).
- **Why the current approach was chosen:** Not recorded as an explicit "we compared these two
  designs" decision. What is recorded is that a single-transcript design keeps *"the chronological
  transcript... intact while prioritizing instructional speech in the generated outputs"*
  (manuscript, Script 4 text) — avoiding data duplication and keeping exactly one source of truth
  per session.
- **What problem it solves:** Achieves the "prioritize the teacher" objective (thesis RQ2) without
  doubling storage or needing to keep two transcripts in sync.
- **What tradeoffs it introduces:** "Prioritization" is not independently visible anywhere as its
  own artifact — a reader/reviewer wanting to see "the teacher-prioritized version" specifically
  would need to look at keyword/minutes *output*, not a transcript, since none exists.
- **What would break if replaced:** Forking a second transcript would need its own persistence
  (`SessionRecord` would need a new column), its own consistency-with-the-original guarantee on
  every chunk update, and would double the JSON payload size of every session record for no
  functional gain over the current weighting approach.
- **Still appropriate?** Yes, and specifically confirmed appropriate by this project's own
  documentation-correction work this session, which found and fixed exactly this
  misunderstanding in the manuscript before it became a real inconsistency claim.
- **Files/functions:** `backend/services/keyword_service.py: build_weighted_text()`,
  `backend/services/minutes_service.py: _key_points(), _label_topic()`,
  `backend/services/audio_service.py: apply_teacher_verification()`.

## 22. Database — SQLite Default, PostgreSQL for the "Real" Deployment Path

- **What was chosen:** `DATABASE_URL` unset → SQLite file; set → PostgreSQL via `psycopg` v3 +
  Alembic migrations.
- **Alternatives considered:** Not recorded as a multi-database comparison (MySQL, MongoDB, etc.
  never mentioned). The recorded choice is specifically *SQLite-as-zero-config-default* vs.
  *Postgres-as-real-deployment-target*, both kept rather than picking only one.
- **Why the current approach was chosen:** Directly documented, tied to a specific, real,
  previously-existing problem: the original design had *"SQLite/no-migrations, zero auth on any
  endpoint"* flagged by an architecture review as a production gap (`CLAUDE.md`, "Production
  Architecture (Round 3)"). Postgres was added specifically to close that gap for anything beyond
  local dev, while SQLite was deliberately *kept* as the default so *"local dev/`pytest` still need
  no infrastructure at all"* — an explicit, stated design goal, not an oversight.
- **What problem it solves:** Zero-friction local development and CI (no database server needed to
  run `pytest`) while still having a real, migration-tracked, concurrent-write-safe database
  available for anything resembling production.
- **What tradeoffs it introduces:** Two database backends means two behaviors to keep in mind — the
  round-6 row-lock fix (`db.refresh(session, with_for_update=True)`) is explicitly a *"no-op on
  SQLite, whose dialect has no `FOR UPDATE`"* — a real behavioral difference between the two paths,
  documented and tested for specifically (a Postgres-only test, skipped otherwise).
- **What would break if replaced:** Dropping the SQLite path would mean every `pytest` run and
  fresh local clone needs a running Postgres instance just to start the app — directly working
  against the "zero infrastructure for local dev" goal this design explicitly serves.
- **Still appropriate?** Yes — proven correct under real contention (round 6's revert-and-confirm
  test), and the dual-path design's own edge case (SQLite's lack of row locking) was specifically
  tested for rather than assumed away.
- **Files/functions:** `backend/database/db.py`, `backend/database/migrations/`, `alembic.ini`.

## 23. Database Schema — Denormalized JSON Columns, Not Per-Segment Tables

- **What was chosen:** One `sessions` row per recording, with `chunk_results`,
  `transcript_segments`, `speaker_segments`, `keywords`, `minutes` all stored as JSON columns —
  no separate `segments` table with a foreign key back to `sessions`.
- **Alternatives considered:** A normalized schema (a `segments` table, a `speaker_turns` table,
  etc.) is the implied, standard alternative for this kind of data.
- **Why the current approach was chosen:** Directly stated in the model's own docstring: *"A
  thesis-prototype session library doesn't need to query across segments relationally — it needs
  one row per session it can hand back whole to Flutter. Revisit if/when real multi-session
  analytics are needed."*
- **What problem it solves:** The API's actual access pattern is "give me this whole session" (`GET
  /sessions/{id}` returns everything at once) — a normalized schema would need a join (or several)
  to reconstruct the same response, for no benefit this project's own query patterns would use.
- **What tradeoffs it introduces:** A real, already-identified cost: `materialize_transcript()`/
  `append_chunk_result()` redo O(n) work on every chunk arrival (a full copy + re-walk from index
  0), making total work O(n²) across a session — *"fine at the chunk counts this project's own
  testing has exercised, a real concern for a full lecture-length session (hundreds to ~1200
  chunks/hour)"* (`CLAUDE.md`, round 7's deferred list). This is a direct, foreseeable consequence
  of the denormalized-JSON design, explicitly acknowledged rather than discovered by surprise.
- **What would break if replaced:** Every read (`to_detail_dict()`) and write
  (`append_chunk_result()`) path would need rewriting against a relational schema — a genuinely
  large refactor, exactly why the docstring frames this as a "revisit later if needed" rather than
  a permanent commitment.
- **Still appropriate?** Yes for the project's actual current scale (a handful of test sessions,
  never a lecture-length production load) — the documented O(n²) cost is a known, bounded, and
  explicitly-deferred issue, not a silent one.
- **Files/functions:** `backend/models/session.py: SessionRecord`,
  `backend/services/session_service.py: materialize_transcript(), append_chunk_result()`.

## 24. Authentication — JWT + `bcrypt` Directly, Not `passlib`

- **What was chosen:** `PyJWT` for tokens, `bcrypt` called directly for password hashing — not
  `passlib`'s `CryptContext`, which is FastAPI's own most commonly documented pattern.
- **Alternatives considered:** `passlib`'s `CryptContext` is the explicitly named and rejected
  alternative — the standard approach this project deliberately did *not* use.
- **Why the current approach was chosen:** A concrete, reproduced bug, not a style preference:
  *"passlib 1.7.4 (unmaintained) breaks against bcrypt>=4.1's changed version metadata
  (`AttributeError: module 'bcrypt' has no attribute '__about__'`) — confirmed against the bcrypt
  version this project installs"* (`backend/core/security.py`'s own docstring). This is a
  first-hand-reproduced compatibility failure, not a general concern about `passlib`'s health.
- **What problem it solves:** Working password hashing without depending on an unmaintained
  compatibility shim that breaks against the actual installed `bcrypt` version.
- **What tradeoffs it introduces:** Slightly more manual code (`hash_password()`/`verify_password()`
  handle bcrypt's 72-byte input limit directly) instead of `passlib`'s abstraction layer — a
  small, deliberate cost in exchange for something that actually works.
- **What would break if replaced:** Reintroducing `passlib` would immediately reproduce the exact
  `AttributeError` this decision exists to avoid, given the `bcrypt` version this project's
  `requirements.txt` resolves to (confirmed `bcrypt==5.0.0` installed this session).
- **Still appropriate?** Yes — directly verified working this session (register/login round-trips
  succeeded via live `curl` testing).
- **Files/functions:** `backend/core/security.py: hash_password(), verify_password(),
  create_access_token(), decode_access_token()`.

## 25. Model Loading — Once Per Process, Never Per-Request

- **What was chosen:** Every ML model (Whisper, Silero, SpeechBrain, pyannote) is loaded exactly
  once per worker process, via the `worker_process_init` Celery signal, and reused for every task
  that process picks up.
- **Alternatives considered:** Loading a model fresh per request/task is the obvious (and much
  simpler) alternative — never adopted, and explicitly forbidden: *"Models loaded once by caller,
  passed in — never reloaded per call"* is "Key Architectural Rule #3" in `CLAUDE.md`, present from
  the earliest tech-stack lock.
- **Why the current approach was chosen:** The cost of the alternative is directly measured:
  *"cold model load ~7.5s (Whisper 4.2s + SpeechBrain 2.9s + Silero 0.4s)"* (`CLAUDE.md`, round 8) —
  reloading that on every single request/task would make the pipeline unusable. A concrete, caught
  regression proves this rule matters in practice, not just in theory: `evaluation/latency.py`'s
  own benchmarking script once forgot to pass in a preloaded Silero model, silently reloading it
  from scratch on every one of its `--runs` iterations, "inflating the exact per-stage latency
  numbers this script exists to produce" (`CLAUDE.md`, round 5) — the same bug recurred
  independently in `evaluation/resources.py` (round 9), showing this is an easy mistake to make
  even inside code whose whole job is respecting this rule.
- **What problem it solves:** Amortizes the ~7.5s cold-load cost across every task a worker process
  ever handles, instead of paying it repeatedly.
- **What tradeoffs it introduces:** A worker process's memory footprint stays permanently elevated
  (every model resident in RAM for the process's whole lifetime) — the cost of statefulness in
  exchange for speed.
- **What would break if replaced:** Every measured latency number in `docs/ML_PIPELINE.md` would
  become meaningless — those numbers assume warm models; per-request loading would make every
  single chunk pay the full ~7.5s cost, making the RTF numbers roughly 3–4× worse.
- **Still appropriate?** Yes, unambiguously — this rule has caught real regressions twice
  (round 5, round 9) precisely because it's actively enforced, not just stated.
- **Files/functions:** `backend/worker/celery_app.py: _load_models(), get_worker_models(),
  _preload_models()`; the eager-mode preload added to `backend/main.py`'s `lifespan()` this session
  extends the same rule to the eager-mode dev path specifically.

## 26. GPU/CPU Selection — CPU Only, No GPU Code Path Exists

- **What was chosen:** Every model runs on CPU. The installed `torch` build in this project's own
  `.venv` is `2.13.0+cpu` — confirmed by direct execution this session (`torch.cuda.is_available()`
  → `False`).
- **Alternatives considered:** **RATIONALE UNKNOWN — implementation exists but historical reasoning
  was not preserved**, in the sense that no document anywhere states "we considered GPU and
  rejected it because X." `WHISPER_DEVICE` exists as a config knob defaulting to `"cpu"`, implying
  GPU was at least anticipated as a future possibility, but SpeechBrain and pyannote have no
  device-selection knob anywhere in this codebase at all — grepped this session, confirmed zero
  `cuda`/`gpu`/`.to(device)` references anywhere in `backend/`.
- **Why the current approach was chosen:** Most plausibly circumstantial rather than deliberate: the
  dev machine has an RTX 3050 (4GB VRAM) with working drivers (confirmed via `nvidia-smi` this
  session), but the specific PyTorch wheel installed is the CPU build — installing a CUDA build
  requires an explicit different pip index URL, which nothing in `requirements.txt` (deliberately
  unpinned, per its own header comment) specifies either way. This reads as "never done," not "done
  and CPU chosen instead."
- **What problem it solves:** N/A — this is an absence of a decision more than a decision, based on
  available evidence.
- **What tradeoffs it introduces:** Every measured performance number in this entire project
  (`docs/ML_PIPELINE.md`) is a CPU number, and the RTF ≈2.4–2.9 slower-than-real-time result is
  directly downstream of this. 4GB VRAM would in any case be tight for running Whisper `small` +
  SpeechBrain + pyannote simultaneously without careful memory management if GPU support were ever
  added — a real engineering constraint on a *future* GPU path, not evidence for or against the
  current CPU-only state.
- **What would break if replaced:** Nothing would "break" — enabling GPU would require both a torch
  reinstall *and* code changes (a device argument threaded through `teacher_verification_service.py`
  and `diarization_service.py`, neither of which currently accepts one at all).
- **Still appropriate?** This is the single most consequential unexamined gap in the whole project:
  the dev machine has a capable GPU sitting unused while the core bottleneck (Whisper transcription
  speed) is exactly the kind of workload a GPU would meaningfully accelerate. Whether it's "still
  appropriate" depends entirely on whether anyone has deliberately decided GPU support isn't worth
  the engineering cost for a thesis prototype — and no such decision is recorded anywhere.
- **Files/functions:** `backend/core/config.py: whisper_device` (the only device knob that exists
  at all, and only for Whisper specifically).

## 27. Asynchronous Processing — Celery Eager Mode as the No-Infrastructure Fallback

- **What was chosen:** When `CELERY_BROKER_URL` is unset, Celery's own `task_always_eager` mode runs
  every "worker" task inline, synchronously, in whichever process called `.delay()`.
- **Alternatives considered:** Requiring a real Redis broker for all local dev/CI/testing is the
  implicit alternative — rejected in favor of a zero-infrastructure default.
- **Why the current approach was chosen:** Directly documented as intentional, not a shortcut:
  *"this is Celery's own documented testing pattern, not a hack, and it's what keeps this app
  runnable in a dev/CI sandbox with no Redis installed"* (`backend/worker/celery_app.py`'s own
  docstring). A related, deliberately-avoided pitfall is also documented: tasks are enqueued via
  imported task objects' `.delay()`, specifically *not* `celery_app.send_task("name", ...)`, because
  the latter *"ignores `task_always_eager` entirely... which would silently break the whole
  eager-mode dev/test/CI path"* — confirmed by observing `AlwaysEagerIgnored` in logs when this was
  tried (`CLAUDE.md`, "Production Architecture (Round 3)").
- **What problem it solves:** `pytest`, local dev, and CI all run the full pipeline logic (including
  worker-tier code) with zero extra infrastructure — no Redis install needed anywhere except a
  genuinely scaled deployment.
- **What tradeoffs it introduces:** A real, reproduced cost this session found and fixed: eager
  mode's first request after a cold start pays the full model-load cost synchronously, which (for a
  WebSocket request specifically) could trip the client's own keepalive timeout — this exact failure
  was reproduced and fixed in `backend/main.py`'s `lifespan()` this session (preloading models at
  startup when eager mode is detected).
- **What would break if replaced:** Removing eager mode would mean `pytest` (and this project's own
  CI) would need a real Redis broker just to run the worker-tier tests (`tests/test_tasks.py`) —
  a significant new CI dependency for no functional gain in what those tests actually verify.
- **Still appropriate?** Yes, and more robust after this session's fix — the one real gap it had
  (the cold-start WS timeout) is now closed and re-verified by reproducing the original failure
  against the fixed code.
- **Files/functions:** `backend/worker/celery_app.py` (`task_always_eager=settings.
  celery_broker_url is None`), `backend/core/pubsub.py` (the matching in-process `asyncio.Queue`
  fan-out for the no-broker case), `backend/main.py: lifespan()`.

## 28. Concurrency — Contiguous-Prefix Materialization for Out-of-Order Chunks

- **What was chosen:** `SessionRecord.chunk_results` (keyed by chunk index) is the single source of
  truth; the visible `transcript_text`/`transcript_segments` are *rebuilt* from the longest
  **contiguous** prefix starting at index 0 — not simply appended in arrival order.
- **Alternatives considered:** Appending each chunk's result as it arrives (in whatever order that
  happens to be) is the simpler, rejected alternative.
- **Why the current approach was chosen:** Directly documented: *"a chunk landing early never makes
  text appear out of order in a live transcript"* (`CLAUDE.md`, "Production Architecture (Round
  3)") — a real risk specifically because chunks can be picked up by different workers and complete
  in a different order than they were sent, once a real (non-eager) worker pool is in play.
- **What problem it solves:** Guarantees a live-streaming transcript never visibly jumps backward or
  shows chunk 3's text before chunk 1's, even under genuine multi-worker race conditions.
- **What tradeoffs it introduces:** The same O(n²)-across-a-session cost already named in §23 — this
  contiguous-prefix rebuild is *why* that cost exists, not a separate issue. A chunk that fails
  permanently would also permanently cap the visible transcript at that point, since nothing after
  a gap can become "contiguous" until the gap is filled — an edge case this design accepts as the
  price of correctness elsewhere.
- **What would break if replaced:** Reverting to arrival-order appending would reintroduce exactly
  the risk this design closes — confirmed as a real concern specifically because of round 8's
  separate, real concurrency bug (below, §not-numbered — see round 6/round 8 lock fix) proving
  genuine multi-worker races do occur in this system.
- **Still appropriate?** Yes — proven correct under real contention: 6 parallel WS sessions × 3
  chunks against a real worker pool + real Postgres, "all finalized cleanly, no lost `chunk_results`"
  (`CLAUDE.md`, round 8).
- **Files/functions:** `backend/services/session_service.py: materialize_transcript(),
  append_chunk_result()`; `tests/test_tasks.py`.

## 29. Error Handling — Broad Per-Task `try/except` + Structured Logging, Not Silent Failure

- **What was chosen:** Every Celery task wraps its full body in `try/except Exception`, publishing
  an `{"type": "error", ...}` pub/sub message **and** logging via the structured logger — a
  deliberately broad exception boundary at exactly one layer (the task's own top level), not
  scattered narrower catches throughout.
- **Alternatives considered:** Letting an exception propagate and rely on Celery's own default
  failure handling (which would leave the client's WS connection hanging, waiting for a chunk result
  that will never arrive) is the rejected alternative — proven to actually happen before this
  pattern was applied everywhere: *"A malformed chunk/enrollment upload could hang a session
  forever"* because `write_temp_audio(base64.b64decode(...))` originally sat *before* the `try:`
  block in two different task functions (`CLAUDE.md`, round 5).
- **Why the current approach was chosen:** Directly documented, and specifically motivated by a
  second, related gap found later: logging failures matters *independently* of the pub/sub message,
  because *"a chunk failure only reaches the pubsub channel while a client is still connected to see
  it... this at least makes it visible in the worker's own logs"* (`CLAUDE.md`, round 5) — i.e., the
  dual reporting (pub/sub + log) closes two different blind spots, not one.
- **What problem it solves:** No failure mode can silently hang a WS session forever, and no failure
  is invisible just because nobody happened to be watching at the moment it occurred.
- **What tradeoffs it introduces:** A session where *every* chunk happens to fail still finalizes as
  `"completed"` with an empty transcript — indistinguishable, from the session record alone, from a
  genuinely silent recording. This is an explicitly accepted, documented ambiguity (`CLAUDE.md`,
  round 5's "deferred" list), not an oversight nobody noticed.
- **What would break if replaced:** Narrower per-line exception handling instead of one broad
  task-level boundary would risk missing exactly the class of bug this pattern was created to catch
  — an exception thrown *before* any narrower try-block even begins.
- **Still appropriate?** Yes — directly exercised and confirmed correct this session (a real
  `{"type": "error", ...}` message was observed during live WS testing when a deliberately induced
  chunk failure occurred, without hanging the connection).
- **Files/functions:** `backend/worker/tasks.py: transcribe_chunk_task(), transcribe_file_task(),
  enroll_teacher_task()`, `backend/core/logging.py`.

## 30. Rate Limiting — `slowapi`

- **What was chosen:** `slowapi` (a Flask-limiter-style library for Starlette/FastAPI), applied to
  `/auth/login`, `/transcribe`, `/teachers/enroll`.
- **Alternatives considered:** **RATIONALE UNKNOWN** for `slowapi` specifically vs. other FastAPI
  rate-limiting options (e.g., `fastapi-limiter`, a custom Redis-backed limiter) — not compared
  anywhere.
- **Why the current approach was chosen:** The *need* for rate limiting at all is well documented
  (an architecture review flagged "no rate limiting" as a production gap, `CLAUDE.md` "Production
  Architecture (Round 3)"), but the specific library choice itself is not justified anywhere.
- **What problem it solves:** Confirmed working, not just configured: *"12 rapid `/auth/login`
  calls: first 10 returned `401`, 11th and 12th returned `429`"* (`CLAUDE.md`, same section) —
  brute-force login protection and basic abuse control on the two other expensive endpoints.
- **What tradeoffs it introduces:** `slowapi`'s default in-memory limiter state doesn't share across
  multiple API-tier processes — a genuinely scaled multi-instance API deployment would need a
  shared backend (e.g., Redis-based) for rate-limit state to be consistent across instances; this
  isn't discussed anywhere in the project's own docs, so it's this document's own inference about a
  gap, not a confirmed limitation the project has hit.
- **What would break if replaced:** `backend/core/rate_limit.py`'s `@limiter.limit(...)` decorator
  usage throughout `backend/api/*.py` is `slowapi`-specific syntax — a swap would touch every
  rate-limited route.
- **Still appropriate?** Functionally yes for a single-instance deployment (this project's actual
  current shape) — the multi-instance gap above is theoretical, not something this project has
  encountered.
- **Files/functions:** `backend/core/rate_limit.py`, `backend/core/config.py: rate_limit_login,
  rate_limit_transcribe, rate_limit_enroll`.

## 31. CORS — `allow_credentials=False`

- **What was chosen:** `CORSMiddleware(allow_origins=["*"], allow_credentials=False, ...)`.
- **Alternatives considered:** `allow_credentials=True` (needed for cookie-based auth) is the
  explicitly named and rejected alternative.
- **Why the current approach was chosen:** Directly documented, and changed from an earlier state:
  round 9 *flipped* this from `True` to `False`, reasoning: *"auth is a Bearer token, never a
  cookie, so credentialed CORS mode does nothing, and `allow_origins=["*"]` + `allow_credentials=
  True` is a combination browsers reject anyway"* (`CLAUDE.md`, round 9; confirmed by this session's
  own reading of `backend/main.py`'s current comment).
- **What problem it solves:** Removes a configuration that did nothing useful (since auth is never
  cookie-based) and would have been actively rejected by browsers had a credentialed request with a
  wildcard origin ever actually been attempted.
- **What tradeoffs it introduces:** None identified — this was a strict correction of a
  configuration that was already not doing anything, not a new capability/restriction tradeoff.
- **What would break if replaced (i.e., reverted to `True`):** Nothing for the Flutter client (not
  a browser, unaffected either way) — but any future browser-based caller sending a credentialed
  request would be silently rejected by the browser itself before the request even reaches this
  server, a confusing failure mode this fix specifically avoids.
- **Still appropriate?** Yes — moot for the actual client (Flutter), correctly configured for any
  hypothetical browser client.
- **Files/functions:** `backend/main.py` (the `CORSMiddleware` registration).

## 32. Redis Addressing — `127.0.0.1`, Never `localhost`

- **What was chosen:** Every Redis connection string in this project defaults to `127.0.0.1`, not
  `localhost`.
- **Alternatives considered:** `localhost` is the conventional, more common choice — explicitly
  rejected here.
- **Why the current approach was chosen:** A concrete, measured, reproduced bug: *"on a dual-stack
  Windows host `localhost` resolves to IPv6 `::1` first, which Memurai doesn't listen on, so
  `redis.asyncio`... eats a ~2s stall — or an outright connect timeout — on every connection"*
  (`backend/core/config.py`'s own comment) — in the actual stress test, this became a hard
  `TimeoutError` that dropped a WebSocket with no close frame (`CLAUDE.md`, round 8).
  `socket_connect_timeout=5` was also added to both pub/sub clients specifically so a genuinely
  down/misconfigured Redis fails fast and loudly rather than hanging for the OS's own much longer
  default timeout.
- **What problem it solves:** Eliminates a multi-second-per-connection stall (or outright failure)
  on Windows specifically, without requiring every developer to know to avoid `localhost` by
  convention.
- **What tradeoffs it introduces:** None identified on Windows; CI's own comment on this exact
  setting is candid that the fix *"likely doesn't reproduce on the Ubuntu runner"* (round 11) —
  applied there anyway purely for consistency with `config.py`'s default, not because CI itself hit
  the bug.
- **What would break if reverted:** Reintroducing `localhost` would bring back the exact multi-
  second stall / connection-drop behavior this fix was built to eliminate, on any dual-stack Windows
  host.
- **Still appropriate?** Yes — a textbook example of a platform-specific bug found, fixed, and
  propagated consistently everywhere the same pattern could recur (`config.py`, `pubsub.py`,
  `.github/workflows/ci.yml`).
- **Files/functions:** `backend/core/config.py: redis_url` default, `backend/core/pubsub.py:
  _REDIS_CONNECT_KWARGS`, `.github/workflows/ci.yml`.

## 33. WebSocket Authentication — Query Parameter, Not a Header

- **What was chosen:** `WS /ws/transcribe?token=<JWT>` — the token travels as a URL query
  parameter, not an `Authorization` header.
- **Alternatives considered:** A header (the pattern used by every other route in this API) is the
  implied, more conventional alternative.
- **Why the current approach was chosen:** Directly documented, and technically forced rather than
  preferred: *"the browser/Flutter WebSocket API can't set custom headers on the opening
  handshake, so a query param is the standard workaround for WS auth"* (`backend/api/
  transcribe.py`'s own docstring).
- **What problem it solves:** Lets the one route that genuinely can't use a header still
  authenticate the same JWTs every other route uses.
- **What tradeoffs it introduces:** A token in a URL is more exposure-prone than one in a header
  (URLs can end up in server access logs, browser history, or proxy logs) — a real, if minor,
  security tradeoff inherent to this workaround, not called out explicitly anywhere in this
  project's own docs as a risk, though it's a well-known general property of query-param auth.
- **What would break if replaced:** There is no drop-in replacement — this is a platform constraint
  (browsers/Flutter's WS client genuinely cannot set a custom header on the handshake), not a
  preference; removing the query param without another mechanism would simply make WS auth
  impossible.
- **Still appropriate?** Yes, given the platform constraint is real and unavoidable. The custom
  close code `4401` for auth failure is a small, deliberate usability addition on top of this
  (lets a client distinguish "bad token" from any other connection failure).
- **Files/functions:** `backend/api/transcribe.py: transcribe_stream()`,
  `backend/core/security.py: get_current_user_from_token_string()`.

## 34. Containerization — Two Separate Docker Images (API vs. Worker)

- **What was chosen:** `deployment/Dockerfile.api` (lean, `requirements-api.txt` only, no FFmpeg)
  and `deployment/Dockerfile.worker` (`requirements-worker.txt`, has FFmpeg) as two entirely
  separate images, rather than one image running both roles.
- **Alternatives considered:** One shared image (running as either API or worker depending on the
  container's start command) is the simpler, rejected alternative.
- **Why the current approach was chosen:** Directly follows from §3 (the API/worker process split)
  — if the API process must never import an ML library, its container image shouldn't carry those
  dependencies (or FFmpeg) either. `Dockerfile.api`'s own comment states this outright: *"Deliberately
  does NOT install ffmpeg or requirements-worker.txt's ML stack: this image never runs
  audio_service, only enqueues Celery tasks."*
- **What problem it solves:** A much smaller, faster-to-build, faster-to-deploy API image, and lets
  the API and worker tiers scale independently (`docker-compose.yml`'s own comment: *"Scale
  independently of the API tier as load grows: `docker compose ... up --scale worker=3`"*).
- **What tradeoffs it introduces:** Two Dockerfiles to keep in sync with their respective
  requirements files, and two build pipelines instead of one.
- **What would break if replaced:** A single shared image would need to install the full ML stack
  (including FFmpeg) even for API-only containers — directly undoing the size/scaling benefit this
  split provides, and reintroducing the risk of the API image accidentally importing an ML library
  it doesn't need.
- **Still appropriate?** Consistent with the codebase's own architecture (§3), but **entirely
  unverified as containers**: neither image has ever actually been built in any environment this
  project has existed in — Docker itself has never been installed anywhere this project has been
  developed. The design is sound by inspection; whether it actually builds and runs is unconfirmed.
- **Files/functions:** `deployment/Dockerfile.api`, `deployment/Dockerfile.worker`,
  `deployment/docker-compose.yml`.

## 35. CI Strategy — Real Postgres/Redis Service Containers, Not Mocks

- **What was chosen:** `.github/workflows/ci.yml` runs the full `pytest` suite against real
  `postgres:16-alpine` and `redis:7-alpine` service containers on GitHub's own infrastructure —
  not SQLite-only, not a mocked database/broker.
- **Alternatives considered:** Running CI purely against SQLite + eager mode (the same
  zero-infrastructure path local dev defaults to) is the simpler, rejected alternative for CI
  specifically.
- **Why the current approach was chosen:** Directly documented: *"This job runs the full pytest
  suite against real Postgres + Redis — the one thing the dev sandbox that built this couldn't
  verify locally (no Docker there). A green run here is the actual proof the Postgres/Alembic path
  works, not just 'written to spec.'"* (`.github/workflows/ci.yml`'s own comment).
- **What problem it solves:** Gives this project a real, repeatable verification of its Postgres/
  Alembic/Redis code paths despite no local environment (across this project's history) ever having
  Docker installed to test those paths directly.
- **What tradeoffs it introduces:** CI runs slower and has more moving parts (service-container
  health checks, environment wiring) than a pure-SQLite CI job would.
- **What would break if replaced:** Reverting to SQLite-only CI would mean the Postgres-specific
  row-lock test (`tests/test_session_service.py`, skipped without a real Postgres `DATABASE_URL`)
  would *never run anywhere*, silently — exactly the kind of regression risk this CI design exists
  to prevent.
- **Still appropriate?** Yes — this is explicitly the *only* place in this project's entire history
  where the Postgres/Redis code paths get continuously, automatically re-verified, and it has
  already caught real bugs this way (the round-3 commit's own body: *"celery_app.send_task()
  silently ignoring eager mode, and the worker process never importing the `User` model"* — both
  found "only by running against actual distributed infra").
- **Files/functions:** `.github/workflows/ci.yml`.

## 36. Flutter State Management — Plain `provider`, No Bloc/Riverpod/Redux

- **What was chosen:** Three app-wide `ChangeNotifier`s (`AuthController`, `SettingsController`,
  `ApiClient` for DI) via the `provider` package — no dedicated state-management framework.
- **Alternatives considered:** **RATIONALE UNKNOWN** — no comparison against `bloc`, `riverpod`,
  `get`, or any other Flutter state-management approach appears anywhere in the codebase or its
  history.
- **Why the current approach was chosen:** Not recorded. What can be observed from the current
  implementation: the app's actual cross-screen shared state is genuinely small (auth status,
  server settings) — every screen's own transient state (loading flags, form values, the live
  transcript string) is plain `StatefulWidget`/`setState()`, suggesting `provider` was sufficient
  for the app's actual complexity, though this is this document's own assessment of *fit*, not a
  recorded justification for the original choice.
- **What problem it solves:** Minimal-ceremony dependency injection and shared, reactive state for
  the few things that genuinely need to be shared app-wide.
- **What tradeoffs it introduces:** `provider`'s manual `context.read<T>()`/`context.watch<T>()`
  calls throughout screens are less structured than a framework like `bloc` would enforce — a real,
  if minor, discipline cost that has produced no documented bugs so far.
- **What would break if replaced:** Every `context.read<AuthController>()`/`context.watch<...>()`
  call site across every screen would need rewriting — a genuinely wide-reaching but mechanical
  change, not a deep architectural one, given how few actual shared-state objects exist.
- **Still appropriate?** Yes — the app's actual state-sharing needs remain small (three providers),
  and no documented pain point suggests a heavier framework is needed.
- **Files/functions:** `android/lib/app.dart`, `android/lib/core/auth_controller.dart`,
  `android/lib/core/settings_controller.dart`.

## 37. Development Methodology — Hybrid Iterative SDLC (thesis-level decision)

- **What was chosen:** A "Hybrid Iterative Software Development Life Cycle," per the thesis
  manuscript's own Chapter 3 — not a strict Waterfall or a named Agile framework (Scrum/Kanban).
- **Alternatives considered:** A single linear (Waterfall-style) process is the explicitly named
  and rejected alternative: *"Rather than a single linear process, system modules are built
  incrementally, tested individually, integrated into a complete pipeline, and refined based on
  technical and user evaluation results"* (thesis manuscript, "Project Development" section).
- **Why the current approach was chosen:** Directly documented in the manuscript itself: *"selected
  because multilingual classroom transcription involves several uncertain factors, including
  classroom noise, code-switching, speaker distance, teacher and student speech overlap, and the
  limited availability of Hiligaynon speech resources"* — i.e., high requirements uncertainty is
  the stated reason for an iterative rather than linear process.
- **What problem it solves:** Lets weaknesses be found and addressed as real integration/bug-hunt
  passes actually occur — and the git history bears this out concretely: the round 5–11 sequence of
  dedicated review/bug-hunt passes documented throughout `CLAUDE.md` Part 2 *is* this methodology in
  practice, not just a claim on paper.
- **What tradeoffs it introduces:** An iterative process without fixed milestones can drift in
  scope — mitigated here by the explicit, separately-documented scope-lock rules (trilingual-only,
  Kinaray-a cut, "no training from scratch," etc.) that keep iteration bounded.
- **What would break if replaced:** Nothing in the code depends on this choice directly — it's a
  process description, not a technical dependency — but the actual development history (thirty-plus
  commits' worth of incremental, review-driven fixes) is genuine evidence the iterative approach was
  actually followed, not merely stated.
- **Still appropriate?** Yes — the project's own git history is itself the strongest evidence this
  methodology was real and effective (every "round" in `CLAUDE.md` Part 2 is one iteration of
  exactly this cycle).
- **Files/functions:** N/A (process decision, not code) — evidenced by `docs/CHANGE_HISTORY.md`'s
  full commit timeline and `CLAUDE.md` Part 2's round-by-round record.

---

## Summary: decisions by rationale-completeness

| Fully documented (what + why + alternatives) | Partially documented (what + some why) | RATIONALE UNKNOWN |
|---|---|---|
| API/worker split (§3) | Flutter/backend split's on-device specifics (§1) | FastAPI itself (§2) |
| Noise suppression's 3-stage history (§9) | Minutes as rule-based, not LLM (§20) | WebSocket-from-day-one, originally (§4) |
| Whisper model size = small (§14) | Kinaray-a exclusion's specific tie to resources (§17) | `record` package choice (§5) |
| LoRA/PEFT over full fine-tune or scratch (§16) | Glossary-based code-switch correction (§18) | Silero VAD choice (§10) |
| TextRank from scratch, not nltk/sumy (§19) | Rate limiting's need (yes) vs. library choice (§30) | SpeechBrain ECAPA choice (§11) |
| JWT + bcrypt direct, not passlib (§24) | | WhisperX/vanilla-Whisper rejection specifics (§13) |
| Model-loaded-once rule (§25) | | No-forced-language mechanism's intent (§15) |
| Contiguous-prefix chunk ordering (§28) | | GPU/CPU — looks like absence of a decision (§26) |
| Broad per-task error handling (§29) | | `slowapi` specifically (§30) |
| CORS allow_credentials fix (§31) | | Flutter `provider` choice (§36) |
| Redis 127.0.0.1 fix (§32) | | |
| WS auth via query param (§33) | | |
| Two-Dockerfile split (§34) | | |
| CI real-service-containers (§35) | | |
| Hybrid Iterative SDLC (§37) | | |

The pattern above is itself informative: **decisions born from a caught bug or a measured cost are
almost always fully documented** (someone had to explain the fix); **foundational technology
choices made before any bug forced a re-examination are almost always undocumented** — nobody had
to write down why they picked FastAPI or Silero VAD, because nothing ever went wrong with the
choice itself. This is a realistic, not unusual, distribution for a single-developer/AI-assisted
thesis prototype, and it's worth naming outright rather than papering over: **this document cannot
manufacture reasoning that was never recorded, and roughly a third of the decisions above have none
to report.**
