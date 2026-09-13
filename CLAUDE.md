# CLAUDE.md — Scaitale (ScAItale)
> Single source of truth for all AI-assisted development sessions.
> Read this file at the start of every Claude Code session before touching any code.

---

## What This Project Is

**Scaitale** is a thesis prototype: a noise-aware, teacher voice-prioritized multilingual classroom transcription and structured minute generation system for Philippine classrooms. It targets real-world Hiligaynon classroom environments where teachers and students naturally code-switch across **three languages only: Hiligaynon, Filipino (Tagalog), and English**.

**Full thesis title:** *"Development and Evaluation of a Noise-Aware Code-Switching Multilingual Speech Recognition and Automated Summarization System for Hiligaynon Classroom Discourse"*

**Title, confirmed:** checked directly against the manuscript's own title page (`THESIS_ Development and Evaluation of a Noise-Aware Code-Switching Multilingual Speech Recognition and Automated Summarization System for Hiligaynon Classroom Discourse (4).docx`, found at repo root) — the line above is the real, current title, character-for-character. README.md's old "Talakayan"/"Academic Discussion Assistant Transcription Application" header was the outdated one and has been corrected to match. See `docs/paper-vs-implementation.md` for the full read of the manuscript's Chapter 1 and Chapter 3 against this codebase.

**Repo name:** `academic-discussion-assistant`

---

## Thesis Objectives (verbatim, as given — the actual source to write the manuscript against)

**General Research Question:** How can a prototype teacher voice-prioritized multilingual classroom transcription and structured draft minute generation system help improve the clarity, accessibility, and usability of information presented during multilingual classroom discussions?

**Specific Research Questions:**
1. How effectively can the proposed system process noisy multilingual classroom audio?
2. How accurately can the system identify and prioritize teacher speech?
3. How accurately can the system transcribe Hiligaynon, Filipino, and English code-switched classroom discourse?
4. How effectively can the system generate structured draft classroom minutes from transcribed speech?
5. How does the system perform in terms of Word Error Rate, Character Error Rate, teacher identification accuracy, and latency?
6. How do students and teachers evaluate the system in terms of usability, perceived usefulness, and perceived comprehension support?

**General Objective:** The study aims to design and develop a prototype teacher voice-prioritized multilingual classroom transcription and structured draft minute generation system that supports the clarity, accessibility, and usability of instructional content in multilingual classroom environments.

**Specific Objectives:**
1. To develop a system for capturing and processing classroom audio in noisy, real-world environments.
2. To implement teacher voice recognition using speaker embedding techniques to identify and prioritize instructional speech.
3. To integrate a multilingual speech recognition model for transcribing code-switched classroom discourse involving Hiligaynon, Filipino, and English, adapting it to Hiligaynon through parameter-efficient fine-tuning, and to evaluate its performance under low-resource language conditions.
4. To generate structured draft classroom minutes including key points, topics, definitions, and tasks from transcribed speech.
5. To evaluate the system's technical performance in terms of transcription accuracy, teacher identification accuracy, and latency.
6. To evaluate the system's usability through user-based assessment of usability, perceived usefulness, and perceived comprehension support.

### Honest status against each objective (updated as of this pass — re-derive, don't assume stale)

| Objective | Status | What's missing |
|---|---|---|
| General | Backend and Flutter client both built and verified end-to-end (emulator); no fine-tuned model, no real-classroom validation yet | Fine-tuning run, real-world testing on a physical device with real classroom audio |
| 1. Capture + process noisy audio | Processing pipeline built and tested on clean lab audio only; client-side capture path now built and verified on-device (emulator, silent virtual mic) | Zero real noisy-classroom audio run through it yet, on a physical device |
| 2. Identify + prioritize instructional speech | Both halves now implemented — identification (SpeechBrain ECAPA) and prioritization (teacher-weighted keywords/minutes, `teacher_speech_ratio`) | Threshold uncalibrated against real enrolled-vs-unenrolled data |
| 3. Multilingual ASR + Hiligaynon fine-tuning + low-resource eval | Whisper integration done; fine-tuning *tooling* ready, adaptation never run; evaluation *tooling* ready, zero real results | The corpus, the training run, the real WER numbers |
| 4. Structured minutes: key points, topics, definitions, tasks | All four now implemented (`definitions` was the gap, closed this pass) | Precision/recall unmeasured until real classroom audio exists |
| 5. Technical evaluation (accuracy, teacher-ID, latency) | Instrumentation complete and proven (`evaluation/`); real per-stage latency + RTF measured on lab audio (round 8) | WER/CER and teacher-ID accuracy still need real classroom audio + human-labeled ground truth; latency on *real* (noisy, long) audio + on target hardware still pending |
| 6. Usability evaluation | Standard SUS scoring math only | No instrument for "perceived usefulness"/"perceived comprehension support" beyond generic SUS yet; needs the finished app + real respondents |

Objectives 2 and 4 were the two gaps where the code didn't yet match what this list actually says — both closed; see "Resolved this pass, round 4" further down.

---

## Working Dynamic

- **Nathan** = Project Manager. Makes all scope and architecture decisions.
- **Claude** = Primary coder and implementer. Step-by-step execution, no replanning.
- No revisiting locked decisions. Forward momentum only.

---

## Tech Stack (Final, Locked)

| Layer | Technology |
|---|---|
| Client | Flutter (Android-first, thin client) |
| Transport | WebSocket — streaming, chunked (2–5s chunks) |
| Backend | FastAPI |
| Middle layer | `backend/services/audio_service.py` |
| Noise suppression | FFmpeg `afftdn` (FFT denoise) filter — was `pyrnnoise`, see "Noise suppression — actual implementation" |
| VAD | Silero VAD |
| Speaker verification | SpeechBrain ECAPA-TDNN (cosine similarity) |
| Diarization | pyannote.audio (optional) |
| Transcription | Faster-Whisper `small`, int8, CPU, multilingual |
| Post-processing | Glossary-based refinement for Hiligaynon/Filipino terms |
| Keyword extraction | TextRank |
| Minutes generation | Rule-based structured output |
| Fine-tuning | LoRA/PEFT on Faster-Whisper small (Hiligaynon corpus) |
| Training platform | Google Colab (free GPU) |

---

## Pipeline Order (Locked)

**Corrected against the actual built code** (`backend/services/audio_service.py: run_pipeline()`) — the order originally planned here had SpeechBrain and pyannote running *before* Faster-Whisper, which turned out not to be implementable as literally stated: teacher verification (as built) slices audio per *Whisper segment* to extract each embedding, and diarization's speaker-label merge (`merge_transcript_with_speakers()`) attaches labels onto Whisper's segments — both structurally need those segments to already exist. The manuscript's own Pseudocode, Level 1 DFD narrative, and Integration Testing sequence (Chapter 3) all still describe teacher-ID running on raw VAD chunks *before* transcription — that's a real, consistent discrepancy against this order, not just this file's own stale draft; see `docs/paper-vs-implementation.md` for the reasoning on why this build's order was kept instead. The real, tested, working order:

```
Flutter (WebSocket chunks)
  → FastAPI
    → FFmpeg normalize + loudnorm (ALWAYS ON, never optional)
    → FFmpeg afftdn denoising (in place at 16kHz) [enable_denoise toggle]
    → Silero VAD          [enable_vad toggle]
    → Faster-Whisper transcription
    → Glossary refinement (applied per-segment, right after transcription)
    → pyannote diarization + speaker-label merge [enable_diarization toggle, OPTIONAL]
    → SpeechBrain ECAPA teacher verification (per Whisper segment) [enable_teacher_verification toggle]
    → TextRank keyword extraction (session finalize, not per-chunk)
    → Rule-based minutes generation (session finalize, not per-chunk)
    → Storage
    → JSON response → Flutter
```

**Toggle flags:**
- `enable_denoise` — FFmpeg `afftdn` denoising (opt-in, off by default)
- `enable_vad` — Silero VAD (False = one synthetic whole-file segment returned)
- `enable_diarization` — pyannote (optional/nice-to-have)
- `enable_teacher_verification` — SpeechBrain ECAPA cosine similarity

**Model loading rule:** Both diarization and Whisper models loaded ONCE by the caller, passed in — never reloaded per call.

---

## Repo Structure (Confirmed)

```
academic-discussion-assistant/
├── android/                  # Flutter client only
├── backend/
│   ├── api/
│   ├── services/             # Middle layer between API and AI modules
│   ├── core/
│   ├── database/
│   ├── schemas/
│   ├── models/
│   ├── utils/
│   └── main.py
├── ai/                       # finetuning/ (LoRA train + convert scripts) is the only thing in here now — whisper/,
│                             # rnnoise/, silero/, pyannote/, speechbrain/ were empty, untracked leftovers from
│                             # early planning (that wrapping logic actually lives in backend/services/ instead)
│                             # and have since been deleted from disk, not just left empty
├── models/                   # Trained weights/embeddings only (NO source code)
├── datasets/
│   ├── raw/
│   ├── clean/
│   ├── processed/
│   └── metadata/
├── recordings/
├── transcripts/
├── experiments/              # Per-experiment folders for thesis results
├── evaluation/                # wer.py, latency.py, teacher_id.py, sus.py, resources.py — flat scripts; the
│                               # wer/cer/latency/ subdirectories once planned were empty leftovers, since deleted
│                               # (same as ai/, above); reports/ and plots/ are the real output dirs
├── docs/                     # DFD.md (Level 0 + Level 1 data flow diagrams), DevelopmentLog.md, future_ideas.md, paper-vs-implementation.md
├── scripts/                  # Dev utilities only, NOT app code
├── tests/
└── deployment/               # Built — Dockerfile.api, Dockerfile.worker, docker-compose.yml (see "Production Architecture" below)
```

**.gitignore must include:** `android/.idea/`
**`license/`** must be a root-level file, not a folder.

---

## Six Built Scripts in `scripts/`

These are dev utilities. Their logic was promoted into `backend/services/`; the scripts were originally frozen after that, but that rule was **lifted in round 10** — they're maintained again (bug fixes, kept in step with `backend/services/` where it matters). `backend/` remains the real thing; the scripts are for local one-off runs.

1. `record_test_audio.py` — mic capture → `recordings/classroom.wav` (16000 Hz mono int16)
2. `preprocess_audio.py` — FFmpeg standardization (16kHz mono PCM WAV, loudnorm)
3. `transcribe_audio.py` — Faster-Whisper `small`, int8 CPU, shared `load_model()`
4. `process_pipeline.py` — full pipeline orchestrator with toggle flags. `standardize_audio()` (FFmpeg, always-on) → `clean_audio()` (afftdn, optional) → VAD → Whisper → diarize + merge. Kept in step with `audio_service.py` (round 10).
5. `simulate_streaming.py` — chunks file into 1–10s pieces (default 3s); full pipeline per chunk. A trailing chunk ≤1s is folded into the previous one (round 10 — a sub-second chunk reliably triggers a Whisper repetition-loop).
6. `diarize_audio.py` — standalone pyannote pipeline; maps raw labels to Speaker A/B/C by first-appearance

**`process_pipeline.py` logic → `backend/services/audio_service.py`** was the first major backend build task (done).

---

## Flutter Client — Preset System

- Presets defined **client-side** in `pipeline_config.dart` (backend is stateless)
- Three presets: `Fast / Balanced / Accurate`
- `toJson()` sends concrete parameter values per request — backend never sees preset names
- Beam size = primary speed/accuracy dial
- Chunk duration = Flutter-side slider (1–10s)
- Advanced settings panel with outcome-framed labels

---

## Chunk Duration Constants

- `MIN_CHUNK_DURATION_SECONDS` and `MAX_CHUNK_DURATION_SECONDS`
- Validated **only** in `split_into_chunks()` — single source of truth, not duplicated in argparse

---

## Data Flow

```
Android (local RMS VAD gate) → FastAPI → Audio Service → afftdn denoise → Silero
→ Whisper → Diarization → Teacher Verification → Database → JSON → Android
```

(Whisper before Diarization before Teacher Verification — see "Pipeline Order (Locked)" above for why that order is structural, not arbitrary. "Android (local RMS VAD gate)" is `android/lib/core/local_vad.dart` — see "Hybrid Edge/Server Design" and "Flutter Client (Built)" — a lightweight energy check deciding whether a chunk is even worth sending, separate from and upstream of the server's own Silero VAD stage.)

---

## Flutter Screens (Required)

1. Home / session library
2. Teacher voice enrollment
3. Live recording + real-time subtitles
4. Transcript view with search and match highlighting
5. Structured minutes view + export
6. Settings (pipeline toggles, preset selector, chunk duration slider)

---

## Evaluation Instrumentation (Built Into Pipeline From Day One)

- Per-chunk latency logged at every pipeline stage
- `evaluation/wer.py` — WER and CER vs reference transcripts
- `evaluation/latency.py` — latency breakdown per stage
- `evaluation/plots/` — metric visualization
- Metrics: WER/CER (by language segment), teacher ID precision/recall/F1, end-to-end latency

---

## Fine-Tuning (IN SCOPE — Non-Negotiable)

- LoRA/PEFT adaptation of Faster-Whisper `small` on Hiligaynon classroom corpus
- Dataset: real classroom recordings by Nathan; naturally occurring Ilonggo code-switched speech
- Format: HuggingFace dataset, 90/10 train/eval split, stored in `datasets/`
- Training: Google Colab free GPU
- Adapters saved to `models/`
- Targeted for second week of September after VAD segmentation + draft transcription by team

---

## Evaluation Metrics (Complete)

- **WER/CER** — overall, AND broken out by language segment (English vs Filipino vs Hiligaynon)
- **Code-switched utterances** — reported separately from monolingual utterances in WER analysis
- **Teacher identification:** precision/recall/F1 AND false-accept/false-reject rate on enrolled vs unenrolled speakers
- **RTF (Real-Time Factor)** — pipeline speed relative to audio duration
- **End-to-end latency** — per pipeline stage
- **Resource usage** — CPU/memory on target hardware
- **Usability** — System Usability Scale (SUS) with actual respondents

---

## Hybrid Edge/Server Design (Architectural Property)

**Status: partially realized.** On-device VAD is now real —
`android/lib/core/local_vad.dart` — but it's a lightweight energy/RMS gate,
not a learned model, and its threshold (~-40 dBFS) is a documented heuristic
default, unvalidated against real classroom audio (same "unmeasured until
real data exists" caveat this file already uses for
`teacher_verification_threshold`). Noise suppression and the offline
fallback path below are still NOT built — don't read either of those two as
already working.

- Local (on-device): **VAD — done.** `PcmChunker` runs `LocalVad`'s windowed
  RMS check (sub-frames, not one average over the whole 2–10s chunk — a
  short real utterance inside an otherwise-quiet chunk would otherwise read
  as silence) on every outgoing chunk before it ever reaches the WS, with a
  1-chunk "hangover" (a chunk immediately following detected speech is still
  sent even if it reads quiet itself) so trailing speech isn't clipped at
  the chunk boundary. The very first chunk of a session is always sent
  regardless of its own content. **Noise suppression — deliberately not
  attempted**: real DSP noise suppression can't be safely validated without
  real audio and a human listening pass; shipping an untested half-measure
  risked silently degrading real speech, which was judged worse than
  leaving it open and documented.
- Server (FastAPI): diarization, teacher verification, Whisper transcription — unchanged, fully server-side
- **Graceful degradation when offline:** still NOT built. A local-record-then-sync fallback needs local storage, a background sync/retry mechanism, and its own UI state — a genuinely larger feature than the VAD pre-filter above, left open.
- Benchmark full pipeline on actual target hardware — isolate model inference vs integration overhead before wiring into Flutter — still open
- If local pipeline too slow: push diarization/verification to server path, keep VAD+denoise local — the VAD half of this is now real; on-device denoise is still server-side only (`afftdn` runs in the worker)

---

## Data Collection Tracking (Fine-Tuning Critical Path)

- Weekly hour-target for raw classroom audio = tracked metric, same as WER
- Nathan recording now — phone recorder in classroom is acceptable for raw collection
- If weekly targets not met by Week 6–7, that is the early warning signal
- Explore existing Hiligaynon/Tagalog ASR corpora to reduce cold-start problem
- Transcription by Nathan + Andrei + Dan Joseph (split duty) is the bottleneck, not GPU training

---

## Explicitly Out of Scope (Defensible)

*Superseded in one place, noted so a reader landing here first isn't misled:* "Cloud infrastructure / production scaling" below was the original scope line — "Production Architecture (Round 3)" further down is an explicit, later, user-requested reversal of that specific boundary (Docker, Postgres, auth, CI). Everything else on this list still stands.

- Training ASR models from scratch
- iOS compatibility
- Full offline mobile deployment
- ~~Cloud infrastructure / production scaling~~ — reversed, see note above and "Production Architecture (Round 3)"
- Polished UI beyond functional prototype
- Full pyannote diarization (optional, not mandatory)
- **Kinaray-a** — explicitly considered and cut; trilingual scope is final
- Deferred features tracked in `docs/future_ideas.md` — ideas go there, not into scope (this file actually lives under `docs/`, not repo root — corrected here; the "Repo Structure" tree above already had it right, this line just hadn't matched)

---

## Language Scope (CRITICAL)

**TRILINGUAL ONLY: Hiligaynon, Filipino, English.**
- "Quadrilingual" anywhere in code, comments, or docs is an ERROR.
- Filipino is the correct designation (not "Tagalog") in academic/manuscript contexts.
- Language order in manuscript: Hiligaynon – Filipino – English (standardized).

---

## Key Architectural Rules

1. FFmpeg preprocessing is ALWAYS ON — never toggleable
2. All subsequent pipeline stages have independent toggles
3. Models loaded once by caller, passed in — never reloaded per call
4. Backend is stateless — receives concrete parameter values, not preset names
5. WebSocket transport from day one — not HTTP POST with polling
6. Single source of truth for chunk validation: `split_into_chunks()` only
7. `process_pipeline.py` is the script whose logic promotes into `audio_service.py`

---

## Development Environment

- **OS:** Windows (PowerShell)
- **Project path:** `C:\Users\natha\OneDrive\Documents\Thesis\academic-discussion-assistant\`
- **Virtual environment:** `.venv` in project root — activate before every session
- **FFmpeg:** installed at `C:\ffmpeg\bin`, on PATH — `ffmpeg` and `ffprobe` both available
- **HF_TOKEN:** required for pyannote (Hugging Face gated model) — set per session with `$env:HF_TOKEN = "your_token"` or permanently via `setx`
- **JWT_SECRET_KEY:** required to run the API (auth can't sign tokens without it) — any value works for dev (`$env:JWT_SECRET_KEY = "dev-only-secret"`); generate a real one with `python -c "import secrets; print(secrets.token_hex(32))"` for anything beyond local dev. In `ENVIRONMENT=production` the API refuses to start without it.
- **PostgreSQL 17:** installed natively (Windows service `postgresql-x64-17`, auto-starts). Dev database: `scaitale` / user `scaitale` / password `scaitale_dev_password` → `$env:DATABASE_URL = "postgresql+psycopg://scaitale:scaitale_dev_password@localhost:5432/scaitale"`. Optional — SQLite is the default when `DATABASE_URL` is unset, and `pytest` needs no infra at all.
- **Memurai (Redis-compatible):** installed natively (Windows service `Memurai`, auto-starts) at `redis://127.0.0.1:6379/0` — set `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND`/`REDIS_URL` to it to run a real separate worker (`celery -A backend.worker.celery_app worker --pool=solo` — `--pool=solo` is required on Windows, prefork needs fork()). Also optional — no broker configured means Celery's eager mode runs tasks inline in the API process. **Use `127.0.0.1`, not `localhost`** — on this dual-stack Windows host `localhost` resolves to IPv6 `::1` first, which Memurai doesn't listen on, so `redis.asyncio` (the WS pub/sub client) eats a ~2s stall or an outright connect timeout per connection before falling back to IPv4. `backend/core/config.py`'s default was changed to `127.0.0.1` for the same reason.
- **Manual smoke tests:** `scripts/v2_smoke_test.py` (full REST+WS walkthrough: register → login → async transcribe+poll → teacher enrollment → WS streaming → /metrics) and `scripts/ws_smoke_test.py` (WS-only) — both expect a server already running on port 8000; both end in an explicit pass/fail. Dev utilities like the six scripts, not app code.
- **Python standard:** no argparse or CLI concerns inside importable functions — CLI entry points are thin wrappers only

---

## Importable Functions (from `scripts/` → future `backend/services/`)

From `preprocess_audio.py`:
- `check_dependencies()` — confirms ffmpeg/ffprobe on PATH
- `validate_input_file(input_path)` — rejects missing or unsupported files
- `inspect_audio(input_path)` → dict — ffprobe metadata extraction
- `preprocess_audio(input_path, output_path)` → Path — FFmpeg standardization

Output of preprocessing: `recordings/lecture_preprocessed.wav`

From `record_test_audio.py`:
- `sd.PortAudioError` wrapped in `main()` — mic failure gives clean message, not raw traceback
- Same error-handling pattern should be applied to FastAPI upload endpoints later

From `process_pipeline.py` CLI flags (for reference):
- `--no-vad` — disables Silero VAD
- `--diarize` — enables pyannote diarization

### Teacher verification slot (unbuilt — critical path)
- Slots in after diarization in `process_pipeline()`
- Will use its own `enable_teacher_verification` flag
- Compares each speaker cluster against enrolled ECAPA embedding via cosine similarity
- `process_pipeline()` signature will gain `teacher_embedding` and `enable_teacher_verification` params
- SpeechBrain ECAPA-TDNN: enrollment endpoint stores embedding, per-chunk cosine similarity scoring, binary teacher/non-teacher label on each segment

---

### Noise suppression — actual implementation
- **FFmpeg `afftdn` (FFT denoise) filter**, applied in place at 16kHz — `backend/services/audio_service.py: clean_audio()`, filter string `DENOISE_FILTER = "afftdn=nr=12:nf=-25:tn=1"`. One `subprocess.run` call, no resample round-trip, no Python dependency, ~0.1s/chunk.
- **Was `pyrnnoise` (RNNoise, 48kHz round-trip).** Dropped after `pyrnnoise` 0.4.3 broke against every installable `audiolab`/`PyAV` combo on Python 3.11 (`ResolutionImpossible` to downgrade — `faster-whisper` needs `av>=11` and old `av` has no py3.11 wheels). PM decision this pass. See `docs/paper-vs-implementation.md` §3.3 and "Resolved this pass, round 8" below.
- The paper says "RNNoise... applied through FFmpeg's `arnndn` filter" — `afftdn` is a *different* FFmpeg filter (FFT vs. RNN), but stays within the paper's "applied through FFmpeg" framing. Manuscript wording to update accordingly; if the RNNoise name must be kept, `arnndn` + a committed `.rnnn` model file is the fallback (rejected here for zero-setup portability).
- `nf=-25` (noise floor, raised from the -50 default — classroom ambient sits above near-silence) and `tn=1` (track non-stationary noise) are an **unvalidated heuristic default**, same caveat as `teacher_verification_threshold`. Tune against real noisy classroom audio once it exists.
- One temp file (`_cleaned.wav`), cleaned up in `run_pipeline()`'s `finally` (and in `clean_audio`'s own failure path).
- `enable_denoise=False` (default) — opt-in, not opt-out. Covered by `tests/test_audio_denoise.py`.
- `scripts/process_pipeline.py` + `simulate_streaming.py` `--denoise` also use `afftdn` now (round 10) — the scripts-are-frozen rule was lifted so they could actually be fixed. `pyrnnoise` is no longer imported anywhere.

### Waveform loading — soundfile not torchaudio
- `_load_waveform()` uses `soundfile` (`sf.read()`) instead of `silero_vad`'s `read_audio()`
- Reason: `read_audio()` pulls in torchaudio's torchcodec backend which requires FFmpeg shared DLLs — not the same as the ffmpeg/ffprobe executables already on PATH (Windows-specific conflict)
- Returns `torch.Tensor` (float32) from numpy array

### Function name collision — CRITICAL
- `transcribe_audio()` exists in **two places** with **different signatures:**
  - `transcribe_audio.py` → takes `(audio_path: Path)` — standalone script version
  - `process_pipeline.py` → takes `(model: WhisperModel, waveform: np.ndarray, speech_segments: list[dict])` — pipeline version
- Never import both into the same module without aliasing

### Whisper segment output fields
Each segment in `whisper_segments` contains:
- `start`, `end` (seconds, float)
- `text` (string)
- `avg_logprob` (float) — confidence proxy, useful for filtering hallucinations
- `no_speech_prob` (float) — silence/hallucination detector
- `speaker` (string, added by merge step) — "Unknown" if no diarization overlap

### process_pipeline.py CLI flags (complete)
- `audio_file` — positional, path to preprocessed 16kHz mono WAV
- `--denoise` — enable FFmpeg `afftdn` denoising (off by default; same filter as `audio_service.py`)
- `--no-vad` — skip Silero VAD
- `--diarize` — enable pyannote diarization
- `--hf-token` — Hugging Face token (or set `HF_TOKEN` env var)
- `--num-speakers` — optional, exact speaker count if known

### diarize_audio.py — key details
- Pipeline: `pyannote/speaker-diarization-community-1`
- Raw output extracted to plain `(start, end, raw_label)` tuples immediately — downstream is library-agnostic
- Speaker labels mapped by first-appearance order: `_letter_for_index()` handles A→Z then AA, AB...
- `run_diarization()` orchestrates load → diarize → format (same shape as `process_pipeline()`)
- Importable functions used by `process_pipeline.py`: `load_diarization_model()`, `diarize_audio()`, `format_speaker_segments()`

### simulate_streaming.py — key details
- Chunk files written as int16 WAV to `{input_stem}_chunks/` subdirectory inside `recordings/`
- Growing transcript built by appending chunk text with space separator
- Cross-chunk speaker continuity explicitly absent — speaker clustering restarts per chunk (documented caveat, not a bug — real fix needs a running known-speakers approach in the backend)
- `DEFAULT_CHUNK_DURATION_SECONDS = 3.0`
- CLI flag: `--chunk-seconds` (not `--chunk-duration`)

### transcribe_audio.py — key details
- `load_model(model_size="small", device="cpu", compute_type="int8")` — shared importable function
- `transcribe_audio(model, audio_path: Path)` — standalone version, takes a path not a waveform
- Output key is `"segments"` (not `"whisper_segments"` — different from process_pipeline.py version)
- `print_results()` is a separate display-only function — not coupled to transcribe logic
- `segments` generator from faster-whisper consumed immediately with `list()` — not lazy

### Function signature reference (CRITICAL — avoid collision)

| Function | File | Signature |
|---|---|---|
| `load_model` | `transcribe_audio.py` | `(model_size, device, compute_type) → WhisperModel` |
| `transcribe_audio` | `transcribe_audio.py` | `(model, audio_path: Path) → dict` with `"segments"` key |
| `transcribe_audio` | `process_pipeline.py` | `(model, waveform: np.ndarray, speech_segments: list) → dict` with `"whisper_segments"` key |
| `load_diarization_model` | `diarize_audio.py` | `(hf_token: str) → Pipeline` |
| `diarize_audio` | `diarize_audio.py` | `(pipeline, audio_path, num_speakers) → list[tuple]` |
| `format_speaker_segments` | `diarize_audio.py` | `(raw_segments: list[tuple]) → list[dict]` |
| `run_diarization` | `diarize_audio.py` | `(audio_path, hf_token, num_speakers) → dict` |
| `merge_transcript_with_speakers` | `process_pipeline.py` | `(whisper_segments, speaker_segments) → list[dict]` |
| `process_pipeline` | `process_pipeline.py` | `(input_path, whisper_model, enable_*, diarization_model, num_speakers) → dict` |
| `split_into_chunks` | `simulate_streaming.py` | `(input_path, chunk_duration_seconds) → list[Path]` |
| `simulate_streaming` | `simulate_streaming.py` | `(input_path, whisper_model, chunk_duration_seconds, enable_*, diarization_model) → dict` |
| `inspect_audio` | `preprocess_audio.py` | `(input_path: Path) → dict` |
| `preprocess_audio` | `preprocess_audio.py` | `(input_path, output_path) → Path` |

## Known Open Issues

- Flutter WebSocket integration: **built and verified end-to-end on an Android emulator** — see "Flutter Client (Built)" below. Real physical-device testing (as opposed to emulator) is still open. **One prerequisite for that test found only while writing it up, not yet exercised**: every `uvicorn backend.main:app` invocation anywhere in this file/README defaults to binding `127.0.0.1` (loopback-only). That's invisible on the emulator, since `10.0.2.2` is QEMU's own alias straight back to the host's loopback — but a physical device on the real Wi-Fi NIC would be refused outright by a loopback-only listener, silently (a hang, not an error the app can show). A physical-device run needs `uvicorn backend.main:app --host 0.0.0.0 --port 8000` specifically, plus a Windows Firewall inbound-allow rule for that port.
- Per-chunk diarization has no cross-chunk speaker continuity (restarts each chunk) — unchanged, still true for streamed WS chunks
- Ethics/consent clearance for classroom recordings — must resolve before September recordings
- Whisper first-segment language lock on code-switched speech — known artifact, accepted
- Single-pass loudnorm (vs two-pass FFmpeg) — known limitation, accepted
- `backend/data/glossary.json` is a starter/example list only, not derived from real Whisper error logs yet — grow it from the September corpus pass
- Teacher-verification cosine threshold (`backend/core/config.py: teacher_verification_threshold`) is a reasonable default, not empirically calibrated — `evaluation/teacher_id.py` exists to score it, but needs real enrolled-vs-unenrolled labeled data to run against
- Minutes generation (topics/key-points/definitions/action-items, teacher-prioritized) is a documented heuristic, not NLP — expect misses on real classroom audio; `definitions`' precision/recall is unmeasured until real data exists to score it against, same as action items always was
- Fine-tuning (`ai/finetuning/`) is a complete, tested-importable scaffold, not a trained model — it has no corpus to train on yet (`datasets/processed/` is empty pending the team's recording + transcription pass) and has never actually been run end-to-end
- SUS scoring (`evaluation/sus.py`) has no respondents yet — it's the scoring math only, per CLAUDE.md's "with actual respondents" still needing actual respondents
- `POST /transcribe`'s whole-file path assumes the API and worker containers share a filesystem/volume (see `deployment/docker-compose.yml`'s `shared-tmp` volume) — object storage (S3-compatible) is the properly distributed fix, not yet built (no infra here to build it against)
- Light concurrency testing done (round 8: 6 parallel WS sessions × 3 chunks against the real worker + Postgres, all clean, no lost updates) — but not sustained *load* testing (dozens of concurrent sessions, hours-long sessions, many workers). Measured single-worker streaming RTF ≈ 2.4–2.9 (Whisper `small` int8 CPU): the pipeline is slower than real-time, so a live session's transcript lags and finalizes minutes after "stop" unless `--concurrency`/worker count is scaled to the offered chunk rate. This is a model/hardware reality, not a bug — GPU or a fine-tuned smaller model is the real lever; `WHISPER_CPU_THREADS` gives ~17%.
- **All Flutter↔backend traffic (login credentials, the JWT, and every raw audio chunk streamed over `/ws/transcribe`) is plain, unencrypted HTTP/WS** — `android/app/src/main/AndroidManifest.xml` sets `usesCleartextTraffic="true"`, necessary because the server has no TLS certificate (a local dev machine on the classroom Wi-Fi, addressed by LAN IP). Anyone else on the same Wi-Fi could sniff it. Acceptable for a thesis prototype on a trusted local network; genuinely not acceptable if this ever serves real classrooms over anything less trusted, or the backend moves off the local network — the fix (a TLS cert + `usesCleartextTraffic="false"`) needs real infra (a reachable hostname, a cert) this sandbox has no way to set up or verify. Not previously called out in either doc, found this pass.
- Docker images themselves (not just CI's postgres/redis service containers) have never been built and run as actual containers — `deployment/docker-compose.yml` is written to spec and CI-adjacent-verified only

**Resolved this pass** (were unbuilt, now built — see "Backend (Built)" below): SpeechBrain ECAPA teacher verification, FastAPI endpoints (POST + WebSocket), transcript persistence, glossary post-processing, TextRank + rule-based minutes, `evaluation/wer.py` + `evaluation/latency.py`.

**Resolved this pass, round 2** (beyond the 14-day list, rest of CLAUDE.md's "Evaluation Metrics (Complete)"): `evaluation/teacher_id.py` (precision/recall/F1, FAR/FRR), `evaluation/sus.py` (SUS scoring), `evaluation/resources.py` (CPU/memory via psutil), and the `ai/finetuning/` LoRA/PEFT scaffold (train + merge/convert-to-CTranslate2) for the "Non-Negotiable" fine-tuning item.

**Resolved this pass, round 3** (production/market-deployment architecture — see "Production Architecture" below): the blocking-event-loop bug (API/worker split via Celery), auth (JWT), Postgres + Alembic migrations, structured logging + Prometheus metrics + optional Sentry, rate limiting + upload-size limits, API versioning (`/api/v1`), consent/deletion (RA 10173 basics), Docker images + docker-compose + CI. Verified for real, not just written to spec: PostgreSQL 17 and a Redis-compatible server (Memurai) installed natively, the Alembic migration run against real Postgres, a genuinely separate worker process proven non-blocking against real Redis, and a green `.github/workflows/ci.yml` run on GitHub's own infrastructure (merged to `main`). Two real bugs were caught only by this — `celery_app.send_task()` silently ignoring eager mode, and the worker process never importing the `User` model (broke the `sessions.owner_id` foreign key outside the single-process path) — both fixed and covered by the merged commit.

**Resolved this pass, round 4** (closing two gaps between the code and the thesis's actual specific objectives): teacher-voice **prioritization**, not just identification — `keyword_service.build_weighted_text()` weights teacher-labeled speech more heavily into TextRank, `minutes_service.py`'s key-point selection and topic labeling both rank teacher segments first, and `teacher_speech_ratio`/`teacher_speakers` are new minutes fields. Also **definitions** extraction (heuristic trilingual pattern matching), the previously-missing fourth item from "key points, topics, definitions, and tasks." Both are no-ops when `enable_teacher_verification` was off, so nothing existing changed behavior.

**Resolved this pass, round 5** (a dedicated multi-angle code-review pass across `backend/` and `evaluation/`, after the Flutter/VAD work — see `docs/DevelopmentLog.md`-style diligence, not a response to a reported bug): nine real, independently-confirmed issues fixed, four of them genuine correctness bugs rather than robustness/style:
- **`glossary_service.py` case-sensitivity crash** — `Glossary._replacements` kept the JSON's original-case keys while lookup was always lowercased; any mixed-case glossary key raised `KeyError` on every match. Reproduced directly (`Glossary({"Sir Ko": "sir ko"}).apply(...)` crashed), fixed by lowercasing the lookup dict's keys, regression-tested in `tests/test_glossary_service.py`. This would have broken the very first mixed-case term added during the September corpus glossary-growing pass.
- **`minutes.py` export dropped a genuine 0% teacher-speech-ratio** — `if teacher_ratio:` treated a real, computed `0.0` (teacher enrolled and verified, but didn't speak that session) identically to the field never having existed, silently omitting the line. Fixed to `is not None`; regression-tested in the new `tests/test_minutes_api.py` (this function had zero direct test coverage before).
- **Temp files could leak past a mid-pipeline exception** — `run_pipeline()`'s and `clean_audio()`'s intermediate WAV cleanup ran *after* their last step succeeded, not in a `finally`, directly contradicting this file's own "temp files cleaned up in finally blocks" privacy claim whenever VAD/transcription/diarization/RNNoise itself raised. Both now wrap cleanup in `finally`.
- **A malformed chunk/enrollment upload could hang a session forever** — `write_temp_audio(base64.b64decode(...))` sat *before* the `try:` block in both `transcribe_chunk_task` and `enroll_teacher_task`; a decode/disk-write failure there skipped the task's own error handling entirely, so no result was ever published and the WS session (or the enrollment's polling) would wait indefinitely for a chunk that would never complete. Moved inside both `try:` blocks.
- Teacher enrollment audio now goes through `ingest_audio()` (FFmpeg standardization) before `load_waveform()`, like every other audio entry point — it was the one path skipping the locked "FFmpeg preprocessing is ALWAYS ON" rule, failing with an opaque "Expected 16000Hz, got Xhz" error on anything not already exactly 16kHz mono WAV (today's Flutter client always sends compliant audio, so this was latent, not yet triggered).
- A failed chunk in `transcribe_chunk_task` is now logged via the structured logger, not just published to a pubsub channel nobody may still be listening on — a session where every chunk happened to fail (e.g. a broken worker model) still finalizes as "completed" with an empty transcript (indistinguishable from a genuinely silent session, a real ambiguity — see "deferred" below), but at least the failure is now visible in worker logs instead of leaving zero trace anywhere.
- The worker now calls `init_db()` defensively at model-load time (idempotent, `checkfirst=True`) — a standalone worker started before the API against a fresh SQLite dev DB used to hit "no such table" the moment a task touched a model.
- `evaluation/latency.py`'s own `benchmark_pipeline()` never set `silero_vad_model` on its `LoadedModels`, so `detect_speech()`'s `silero_vad_model or load_silero_vad()` fallback silently reloaded Silero from scratch on every one of its `--runs` iterations — inflating the exact per-stage latency numbers this script exists to produce. Fixed to load it once, matching how the real worker does it.
- Two stale/incorrect code comments fixed: "Filipino / Tagalog" in `keyword_service.py` (this file's own CRITICAL language-scope rule — "Tagalog" anywhere in code/comments/docs is an error) and `SessionRecord.status`'s inline comment (claimed `processing` was a real value and omitted `interrupted`, which is).

**Resolved this pass, round 6** (the highest-value item from round 5's deferred list — a real correctness fix, not just cleanup): `session_service.append_chunk_result()`'s unlocked read-modify-write of `chunk_results` is fixed with `db.refresh(session, with_for_update=True)` — a real row lock on Postgres (a no-op on SQLite, whose dialect has no `FOR UPDATE`; SQLite serializes writes at the whole-database level anyway). **Proven, not just reasoned about**: `tests/test_session_service.py` (new, skipped unless `DATABASE_URL` already points at a real Postgres) spins up two threads, each with its own DB session, both calling `append_chunk_result` for different chunks of the same session with an injected delay to force real lock contention — run directly against this machine's native Postgres. Confirmed the fix matters by temporarily reverting it: **the test reliably failed** (`got ['1']`, chunk `"0"` silently lost) without the lock, and reliably passed (5/5 runs, no flakiness) with it restored. Because CI's own service containers already set `DATABASE_URL` to a real Postgres, this test runs for real on every future CI run too, not just today — continuous, automatic re-validation of this fix, not a one-time check.

**Resolved this pass, round 7** (a dedicated edge-case sweep of the real-audio-ingestion path, triggered directly by real classroom audio being imminent — not a response to a reported bug): five concrete edge cases found and fixed, each with a regression test:
- **Phone-recorder formats were rejected outright** — `SUPPORTED_EXTENSIONS` (duplicated between `backend/services/audio_service.py` and `scripts/preprocess_audio.py`, kept in sync by convention) only listed studio-ish formats (`.wav`/`.mp3`/`.m4a`/`.ogg`/`.webm`/`.flac`/`.aac`). A real classroom recording from a basic Android voice-recorder or phone-call-recorder app (`.3gp`/`.3gpp`/`.amr`), or a phone/camera app used just to capture room audio (`.mp4`/`.mov`), would have been rejected with "Unsupported file type" despite FFmpeg (confirmed directly: `ffmpeg -demuxers` lists `amr`, `mov,mp4,m4a,3gp,3g2,mj2`, and `asf` for `.wma`) being fully able to decode it — the allowlist was stricter than the actual decoder. Both copies widened to also accept `.3gp`, `.3gpp`, `.amr`, `.mp4`, `.mov`, `.opus`, `.wma`; `tests/test_audio_extensions.py` (new) asserts both copies stay in sync and cover the expected set.
- **`POST /transcribe` could turn a valid upload into an unsupported one** — a filename ending in a bare "." (e.g. `"recording."`) has `"."` in it, so the old suffix logic (`"." + filename.rsplit(".", 1)[-1]`) produced a bogus `"."` suffix — not in `SUPPORTED_EXTENSIONS`, so `ingest_audio()` rejected an otherwise-fine file before FFmpeg ever saw it. Factored into a pure, tested `_suffix_from_filename()` helper that falls back to `.wav` whenever the extracted extension is empty, not just when there's no filename at all; `tests/test_transcribe_api.py` (new) covers the normal, no-extension, no-filename, and trailing-dot cases.
- **A malformed `Content-Length` header crashed the upload-size guard itself** — `MaxUploadSizeMiddleware.dispatch()`'s `int(content_length)` ran unguarded; a non-integer value (only plausible from a hand-crafted/malicious request, since every real client sends a valid one) raised an uncaught `ValueError`, turning a request this middleware couldn't even evaluate into a raw 500 instead of a clean 4xx. Now caught and returned as `400`; regression test added to `tests/test_rate_limit.py`.
- **A non-UTF-8 reference transcript crashed `evaluation/wer.py`'s CLI with a raw traceback** — a human (Nathan/Andrei/Dan Joseph) typing a Hiligaynon/Filipino/English reference transcript on Windows can easily save it in the system ANSI codepage (Notepad's historical default), not UTF-8. `UnicodeDecodeError` is a `ValueError` subclass, not an `OSError`, so `main()`'s `except OSError` let it fall straight through uncaught instead of the same clean `"Error: ..."` + `exit(1)` every other bad-input path here gets. Now caught with a message telling the user to re-save as UTF-8; regression test in `tests/test_wer.py` reproduces it with a real cp1252-encoded fixture file.
- **`inspect_audio()` could silently misreport a real file's duration as 0.00s** — `probe_data["format"].get("duration", 0.0)` isn't populated by every container FFmpeg accepts (some `.webm`/`.opus` captures only populate it on the audio stream itself); now falls back to the audio stream's own `duration` field before defaulting to `0.0`. Metadata-printout-only (the pipeline's own duration always comes from the decoded waveform length, never this), so no test added — a print-only fix.

**Found and deliberately deferred, same pass** (real, lower-urgency-or-larger-scope — not fixed, not forgotten):
- `materialize_transcript()`/`append_chunk_result()` redo O(n) work (a full copy + full re-walk from index 0) on every single chunk arrival, making total work and total DB bytes written O(n²) across a session — fine at the chunk counts this project's own testing has exercised, a real concern for a full lecture-length session (hundreds to ~1200 chunks/hour).
- Teacher verification calls SpeechBrain once per Whisper segment with no batching (40-60 sequential CPU forward passes for a typical discussion) — real per-chunk overhead a busier deployment would feel, not a bug. (The old RNNoise 3-FFmpeg-subprocess-per-chunk cost is gone — `afftdn` is one subprocess, ~0.1s; see round 8.)
- `evaluation/wer.py`'s edit distance allocates a full O(n·m) matrix (not a rolling buffer) even for character-level CER on a full session transcript, and `compute_error_rates_by_group()`'s "overall" figure re-runs the whole thing on the concatenated corpus instead of aggregating already-computed per-pair results. `evaluation/teacher_id.py`'s precision/recall/FAR/FRR render as `0.0` (not "undefined") when their denominator is zero. Both are evaluation-script-only (never on any production request path), lower urgency until real evaluation runs are actually happening at a scale where either matters.
- Minor duplication noted, not refactored: `write_report()` is copy-pasted near-identically across all five `evaluation/*.py` scripts; `minutes.py`'s `_get_session_or_404` helper isn't reused by `sessions.py`/`teacher.py`'s equivalent inline checks. (`backend/utils/errors.py` — dead code — was deleted in round 9; `audio_service.py`'s `_run_ffmpeg_resample` in round 8.)
- **`LICENSE` at the repo root is an empty directory, not a file** — a direct violation of this file's own "must be a root-level file, not a folder" rule. Not fixed: what license to actually apply is Nathan's call, not something to invent.

**Resolved this pass, round 8** (a full-stack stress + integration + front-end/back-end audit against a REAL running API + REAL separate Celery worker + REAL Postgres + REAL Redis — not eager mode — plus the first real per-stage latency/RTF numbers; triggered by "stress test this, make it production-level"):
- **Noise suppression was completely broken** — `enable_denoise` / the "Accurate" preset. `pyrnnoise` 0.4.3 (last release) raises deep inside `audiolab` on every call (`audiolab` 0.5.2's `rate`→`sample_rate` rename is pervasive; 0.5.1 fails to import on PyAV≥14; no PyAV old enough to satisfy `audiolab` 0.5.1 still installs on py3.11 alongside `faster-whisper`). **Zero test coverage** is why it went unnoticed. On top of that, `clean_audio()`'s `finally` did raw `.unlink()` on files `audiolab` still had open → `PermissionError [WinError 32]` that *replaced* the real exception in the traceback, plus a permanent temp-file leak. **Fixed:** `clean_audio()` now uses **FFmpeg's `afftdn`** filter (PM decision — see "Noise suppression — actual implementation" and `docs/paper-vs-implementation.md` §3.3): in place at 16kHz, one subprocess, ~0.1s/chunk, no Python dependency. `pyrnnoise`/`audiolab` removed from requirements; `_run_ffmpeg_resample` + `RNNOISE_SAMPLE_RATE` deleted. New `tests/test_audio_denoise.py` (4 tests incl. a real noise-floor before/after and a filtergraph-validity check).
- **Multi-chunk streaming transcript timestamps reset to 0 every chunk** — each streamed chunk is transcribed as its own standalone audio unit, so its whisper/speaker segment times come back chunk-relative (0-based); `materialize_transcript()` just concatenated them, so on a real multi-chunk session every chunk's segments restacked at 0..Ns. The transcript view's timestamps were all wrong and the minutes topic-grouping saw one pile of overlapping segments. **Fixed:** `materialize_transcript()` now shifts each contiguous chunk's segments by the summed audio duration of the preceding ones. `minutes["duration_seconds"]` also switched from "end of last segment" to the authoritative `SessionRecord.duration_seconds`. Verified end-to-end against the real stack: a 3-chunk (3+2+3s) session produced monotonic `[(0,2.04),(2.04,3),(3,5),(5,7.04),(7.04,8)]` and `duration_seconds=8.0`. New tests in `tests/test_tasks.py`.
- **Redis by `localhost` stalled or timed out every WS connection** — on this dual-stack Windows host `localhost` → `::1` first, which Memurai doesn't listen on; `redis.asyncio` (the WS pub/sub client) ate ~2s per connection waiting for the `::1` refusal, and in the stress test hit an outright `TimeoutError` that dropped the WebSocket with no close frame (client saw a raw `ConnectionClosedError`). **Fixed:** `config.py` default → `redis://127.0.0.1:6379/0`; `pubsub.py` both clients get `socket_connect_timeout=5`; `transcribe_stream` now catches a pub/sub-backend failure and sends one clean `error` frame + closes instead of dropping the socket. CLAUDE.md's documented env values updated.
- **Flutter "Share minutes" was 100% broken** — `ApiClient.exportMinutes()` routed through `_handle()`, whose 2xx branch runs `jsonDecode()` on the body — but minutes export returns markdown/plain text, so every *successful* export threw a `FormatException` and the share silently did nothing. **Fixed:** split `_handle()` into `_handle()` (JSON) + `_ensureOk()` (status/401 only, no decode); export uses the latter, and its screen handler now catches non-`ApiException` errors too. New `android/test/api_client_test.dart` (4 tests) — `ApiClient` had no test coverage at all before.
- **Concurrency correctness holds up:** 6 parallel WS sessions × 3 chunks (18 chunk tasks) against the real worker + real Postgres all finalized cleanly, no lost `chunk_results`, no 500s, no hangs — the round-6 row-lock fix and the out-of-order-chunk handling are solid under real contention.
- **First real latency numbers** (dev machine, 8-core CPU, Whisper `small` int8, `recordings/lecture_preprocessed.wav` 5s clip): cold model load ~7.5s (Whisper 4.2s + SpeechBrain 2.9s + Silero 0.4s); warm per-stage on a 5s clip — preprocess ~0.26s, denoise (`afftdn`) ~0.1s, VAD ~0.3s, transcribe ~7–11s. **Streaming RTF ≈ 2.4–2.9** (a 3s chunk takes ~8.6s to process on one worker) — Whisper `small` int8 on CPU is simply slower than real-time; the async worker-pool split is what keeps this from blocking anything, and `--concurrency=N` / more worker containers is the throughput lever. Silero-load-once (round-5 fix) measured 2.8× on `detect_speech`. `WHISPER_CPU_THREADS` env knob added (set to physical core count → ~17% faster single-stream; leave 0 under a multi-worker pool).
- **Teacher-ID functional check** (synthetic, NOT manuscript numbers — real numbers need labeled data): enrolled on a voice, same voice scored cosine 0.66–0.88 (>0.35 threshold → is_teacher), a pitch-shifted proxy 0.12, silence 0.06, white noise 0.04 — clean separation, threshold behaves sanely. End-to-end through the real worker: a verified session correctly labelled 3/3 segments.

**Resolved this pass, round 9** (continued bug-hunt across the code paths round 8 didn't reach — diarization, keyword/glossary services, DB layer, the remaining Flutter screens):
- **Diarization output parsing was wrong for the community-1 model** — `diarize_audio()` did `for turn, speaker in output.speaker_diarization`, but `pyannote/speaker-diarization-community-1`'s `Pipeline.__call__` returns a `DiarizeOutput` dataclass whose `.speaker_diarization` is a pyannote `Annotation`; iterating an Annotation yields `Segment` objects (2-tuples of floats), so `turn, speaker` unpacked to `(start_float, end_float)` and then `turn.start` blew up `AttributeError` on **every** real diarization run. Untested (needs the gated HF model — `enable_diarization` is off by default but the "Accurate" preset turns it on). **Fixed** to `output.speaker_diarization.itertracks(yield_label=True)` per pyannote's own `DiarizeOutput.serialize()`, and made robust to a bare `Annotation` (older 3.x) too.
- **`resources.py` had the same Silero-reload bug round 5 fixed in `latency.py`** — it built `LoadedModels(...)` with no `silero_vad_model`, so `detect_speech()` reloaded Silero from scratch *inside* the monitored run, inflating the exact CPU/memory numbers the script measures. Fixed the same way (load once, pass in).
- **`keyword_service`: PageRank could fail to finalize a session** — `nx.pagerank` raises `PowerIterationFailedConvergence` on a pathological co-occurrence graph (rare on natural text, but a session *must* still finalize). Now `max_iter=200` + a weighted-degree-centrality fallback.
- **`glossary_service` hardening** — an empty/whitespace key in a hand-edited `glossary.json` compiled to `\b(?:...|)\b`, which matches the zero-width position at every word boundary → the replacement got spliced in all over every transcript. Now filtered out. Also catches `UnicodeDecodeError` on a non-UTF-8 `glossary.json` (the file is meant to be grown by hand from the corpus pass; a Windows editor saving it as ANSI would otherwise crash worker startup with a bare traceback).
- **`db.py`: `pool_pre_ping=True`** — a Postgres connection idle past the server timeout (or dropped by a restart) now reconnects transparently instead of failing one request with a stale-connection `OperationalError`.
- **WS handler held a Postgres connection "idle in transaction" for the whole recording** — `transcribe_stream`'s `db` session (kept open for the life of the WS connection by `Depends(get_db)`) does a couple of reads at connection start, then the stream loop runs for minutes with nothing touching `db`. The transaction those reads opened stayed open the entire time — pinning a pooled connection and holding back Postgres autovacuum, per active recording. Now `db.rollback()` right before the loop closes it; `finalize_and_close()` opens a fresh one when it needs to. Verified against the real stack: `pg_stat_activity` shows zero `idle in transaction` after a session (was one per session). The two scalars the loop closures need (`session_id`, `options`) are captured before the rollback.
- **Flutter robustness**: `home` + `enrollment` delete handlers caught only `ApiException`, so a network error during a delete was an unhandled async error with zero user feedback — added the same generic catch the `_load` paths already have. Home-screen `_load()` after returning from the recording screen is now `mounted`-guarded (a 401 mid-recording force-logs-out and disposes the screen). `transcript_screen`'s search highlighter could `RangeError` if a query character changed length when lowercased (ß/İ/ligatures — near-impossible for HIL/FIL/ENG but a hard crash if hit) — now falls back to un-highlighted text in that case. `PcmChunker.flush()` drops a sub-VAD-frame trailing remainder instead of shipping a ~1ms "WAV" the server's FFmpeg rejects as empty (spurious "chunk error" at session end).
- **CORS `allow_credentials`** flipped `True`→`False` in `main.py` — auth is a Bearer token, never a cookie, so credentialed CORS mode does nothing, and `allow_origins=["*"]` + `allow_credentials=True` is a combination browsers reject anyway. (Moot for the Flutter client — not a browser — but a latent misconfiguration for any browser caller.)
- **Dead code deleted**: `backend/utils/errors.py` (`as_http_exception`, imported nowhere).

**Resolved this pass, round 10** (the "scripts are frozen" rule was **lifted by the PM** — `scripts/` is maintained again; these were the broken bits, all now runnable end to end against `recordings/lecture_preprocessed.wav`):
- **`process_pipeline.py --denoise` was broken** the same way the backend's was — `pyrnnoise` 0.4.3 raises in `audiolab`. Switched to FFmpeg `afftdn` (same `DENOISE_FILTER` string as `audio_service.py`); deleted `_run_ffmpeg_resample` + `RNNOISE_SAMPLE_RATE`.
- **`process_pipeline.py` had no standardization step at all** — it went straight to transcription, so on `recordings/lecture_preprocessed.wav` (a short clip ending mid-word) Faster-Whisper hit a repetition-loop hallucination: 25 segments, `"...give a test of a test of a test..."`, timestamps running to 28s for a 5s file. Added an always-on `standardize_audio()` (FFmpeg 16kHz mono + loudnorm, mirrors `ingest_audio()`) — CLAUDE.md rule 1, which the script never actually followed. With it: 2 clean segments, correct text. `process_pipeline()` also now cleans its FFmpeg intermediates in a `finally`.
- **`diarize_audio.py` had the same `output.speaker_diarization` unpacking bug** as `diarization_service.py` (round 9) — `for turn, speaker in ...` on a pyannote `Annotation` unpacks `Segment` float-tuples, then `turn.start` → `AttributeError` on every run. Fixed to `.itertracks(yield_label=True)`, robust to a bare `Annotation`.
- **`simulate_streaming.py`** inherited both fixes via `process_pipeline`; its `--denoise` help text updated. `split_into_chunks()` now folds a trailing chunk of ≤`MIN_CHUNK_DURATION_SECONDS` into the previous one instead of writing it out — a ~1s tail chunk reliably triggered the Whisper repetition loop (observed: one spinning 77s and returning `""`). Verified: a 5s file at `--chunk-seconds 2` now yields 2 chunks (2s + 3s) with a coherent combined transcript, no stall.
- `transcribe_audio.py` and `record_test_audio.py` were checked and work as-is (path-based Whisper decode via `av` 18 is fine; `sd.rec` mic capture unchanged).
- `evaluation/latency.py` + `resources.py` `--denoise` help strings updated to "afftdn".

**Resolved this pass, round 11** (continued bug-hunt; one real crash found and proven with a revert-and-confirm cycle, plus infra/doc cleanup):
- **A failed swipe-delete crashed the session list on the next reload** — `SessionListTile`'s `Dismissible` animates itself out of the tree and calls `onDismissed` exactly once, before the async delete resolves. `HomeScreen._delete()` only removed the session from `_sessions` on a *successful* server delete, so after a failed one (network error, 500, or a race), the next rebuild of the list (pull-to-refresh, or returning from a new recording — both call `_load()`) recreated a `Dismissible` with the same key on the already-"dismissed" `State`, and Flutter throws: `"A dismissed Dismissible widget is still part of the tree."` Reproduced directly with a widget test (swipe → confirm → fail the DELETE call → pull to refresh), confirmed the fix resolves it, then confirmed reverting the fix makes the test fail again. Fixed: remove the item unconditionally, before the server call even resolves — a failed delete still shows its error snackbar and self-heals on the next `_load()`. New `android/test/home_screen_test.dart`.
- **`ScaitaleApp`'s auth gate had zero test coverage** despite being the single most load-bearing piece of app-wide behavior (`MaterialApp(home: auth.isAuthenticated ? HomeScreen : LoginScreen)`, rebuilt on every `AuthController.notifyListeners()`). Added `android/test/app_auth_gate_test.dart` confirming both login and `forceLogout` actually swap the visible screen on this Flutter version (they do — this was a real doubt worth resolving empirically, not by reading Flutter's source and guessing).
- **A double-tap on "New session" could push two `LiveRecordingScreen`s** before the route transition covered the FAB, both trying to grab the microphone. Guarded with the same in-flight-boolean idiom already used elsewhere in this app (`_isSubmitting`, `_isExporting`).
- **CI's Redis URLs** switched to `127.0.0.1` (matching `config.py`'s round-8 default) for consistency, even though the Windows-specific `::1` stall this guards against likely doesn't reproduce on the Ubuntu runner.
- Stale `pyrnnoise`/RNNoise mentions cleaned up in `requirements-api.txt`'s header comment and `Dockerfile.worker`'s comment (afftdn is a plain FFmpeg filter, not a Python package, in both places now). `.dockerignore` gained `*.docx` — the thesis manuscript must never end up in a Docker build context either, not just out of git.
- **Newly documented, not fixed**: all Flutter↔backend traffic (login credentials, the JWT, every raw audio chunk over `/ws/transcribe`) is plaintext HTTP/WS — `AndroidManifest.xml` sets `usesCleartextTraffic="true"` because the dev server has no TLS cert. Acceptable on a trusted classroom Wi-Fi; a real gap if this backend ever serves anything less trusted. See "Known Open Issues".

**Round 3 — production/market-deployment rearchitecture** (explicit scope change past CLAUDE.md's original "no production scaling" boundary, at the user's request after an architecture review): see "Production Architecture" below. This is a real rearchitecture, not additive — `backend/main.py` no longer loads any ML models, `POST /transcribe` is now async (202 + poll), and every route requires auth. The bullets right below this describe the CURRENT shape; treat mentions of "SQLite" or "synchronous" pipeline calls elsewhere in this file as historical unless a bullet here says otherwise.

---

## Backend (Built)

Everything below lives in `backend/` and `evaluation/`, promoted from the six scripts. (The scripts were frozen after promotion; that rule was lifted in round 10 — see "Six Built Scripts" above.)

- **`backend/services/audio_service.py`** — the pipeline orchestrator, unchanged by the Round 3 rearchitecture (only *what calls it* changed — see "Production Architecture"). FFmpeg preprocessing runs unconditionally on every chunk/file (`ingest_audio()`), per the locked "always on" rule. Denoise (`afftdn`)/VAD/diarization/teacher-verification stay independently toggleable. Per-stage latency recorded on every call.
- **`backend/services/teacher_verification_service.py`** — SpeechBrain ECAPA-TDNN (`spkrec-ecapa-voxceleb`), cosine similarity against enrolled embeddings, lazy-imported so a missing install degrades gracefully (disables `enable_teacher_verification`) instead of crashing the worker. Labels each segment `is_teacher`/`teacher_name`/`confidence` — the *identification* half of "teacher voice-prioritized"; `keyword_service.py`/`minutes_service.py` below are the *prioritization* half.
- **`backend/services/glossary_service.py`** + **`backend/data/glossary.json`** — case-preserving glossary correction, applied per-chunk right after transcription.
- **`backend/services/keyword_service.py`** — TextRank on `networkx` (no nltk/sumy), trilingual stopword list. `build_weighted_text()` repeats teacher-labeled segments in the token stream before extraction, so instructional speech dominates the keyword graph instead of getting diluted by side conversation — a no-op when `enable_teacher_verification` was off (no `is_teacher` labels to weight).
- **`backend/services/minutes_service.py`** — rule-based topics/key-points/definitions/action-items/participants, run once per session at finalize. Teacher-labeled segments are ranked ahead of everyone else's for both key-point selection and topic labeling (again a no-op without teacher-verification data); `teacher_speech_ratio` and `teacher_speakers` (majority-teacher diarized labels) are new top-level fields on the minutes dict. `definitions` is heuristic trilingual pattern matching ("X is a Y", "X ay isang Y", "X amo ang Y", etc.) — same "pattern matching, not NLP" caveat as action items, precision/recall unmeasured until real classroom audio exists to score it against.
- **`backend/database/`, `backend/models/`** — Postgres via SQLAlchemy + Alembic migrations (SQLite by default locally/in tests — see "Production Architecture"). One denormalized `sessions` row per recording (JSON columns for segments/keywords/minutes, `owner_id`-scoped) and one `teacher_enrollments` row per enrolled teacher (also `owner_id`-scoped). A new `users` table backs login.
- **`backend/api/`** (all mounted under `/api/v1`, all requiring a bearer token) — `POST /transcribe` (async: 202 + enqueue, client polls `GET /sessions/{id}`) and `WS /ws/transcribe` (`?token=` query param; `start` JSON control frame → binary WAV chunk frames → `end` JSON control frame, mirroring `simulate_streaming.py`'s growing-transcript pattern over the wire, now via a worker pool + pub/sub fan-out instead of running inline); `GET /sessions`, `GET /sessions/{id}`, `DELETE /sessions/{id}` (session library + transcript view + RA 10173 purge); `POST /teachers/enroll` (also async), `GET /teachers`, `GET /teachers/{id}`, `DELETE /teachers/{id}`; `GET /sessions/{id}/minutes`, `GET /sessions/{id}/minutes/export` (markdown/txt download); `POST /auth/register`, `POST /auth/login`.
- **`evaluation/wer.py`** — WER/CER via from-scratch edit distance (no `jiwer`), with a by-group breakdown hook for language/code-switching splits.
- **`evaluation/latency.py`** — aggregates the `stage_latencies` every pipeline call already returns, computes RTF, writes JSON reports + a matplotlib bar chart.
- **`evaluation/teacher_id.py`** — precision/recall/F1 + false-accept/false-reject rate from labeled (predicted, actual) segment pairs.
- **`evaluation/sus.py`** — standard 10-item System Usability Scale scoring + Bangor/Kortum/Miller adjective bands; scoring math only, needs real respondent data.
- **`evaluation/resources.py`** — CPU/memory sampling (via `psutil`) around any pipeline run.
- **`ai/finetuning/`** — LoRA/PEFT fine-tuning of `openai/whisper-small` (`finetune_whisper.py`) + merge-and-convert-to-CTranslate2 (`convert_to_faster_whisper.py`) so a fine-tuned model drops straight into `backend/services/audio_service.load_whisper_model()` via `WHISPER_MODEL_SIZE`. Imports clean and its error paths are exercised, but it has never trained against real data — see `ai/finetuning/README.md`.
- **`tests/`** — pytest coverage for the pure-logic services (glossary, keywords, minutes, WER, teacher-ID metrics, SUS scoring, resource sampling) — nothing that needs the actual model weights or trained checkpoints.

Search/highlighting in the transcript view is intentionally not a backend endpoint — the full transcript + per-segment timestamps already comes back from `GET /sessions/{id}`, so it's client-side substring matching in Flutter.

---

## Production Architecture (Round 3)

Triggered by an architecture review that found: `async def` routes calling CPU-bound pipeline code synchronously (blocked the whole event loop during transcription — measured RTF > 1, a live bug, not hypothetical), no horizontal scaling story for inference, SQLite/no-migrations, zero auth on any endpoint (including uploading classroom audio), no observability, no containerization/CI, no rate limiting, no privacy/consent controls. Closed with standard, well-known patterns — nothing bespoke.

**API / worker split** — the actual fix for the blocking bug. `backend/main.py` is the API tier: FastAPI only, loads no ML models, verified (`import backend.api.transcribe; import backend.api.teacher` — checked against `sys.modules`) to never transitively import torch/faster-whisper/pyannote/silero_vad/speechbrain/pyrnnoise. `backend/worker/celery_app.py` + `backend/worker/tasks.py` are the worker tier: a separate process (`celery -A backend.worker.celery_app worker`) that actually runs `audio_service.run_pipeline()`, with models loaded once per worker process (`worker_process_init` signal — same "loaded once" rule, relocated). `POST /transcribe` returns `202` and enqueues; the client polls `GET /sessions/{id}`. WS chunks are enqueued on receipt (non-blocking) and results come back via `backend/core/pubsub.py` — real Redis pub/sub when `CELERY_BROKER_URL` is set, an in-process `asyncio.Queue` fan-out otherwise (faithful stand-in *only* because `CELERY_TASK_ALWAYS_EAGER` makes the "worker" run inline in that one no-broker case). Tasks are enqueued via imported task objects' `.delay()`, not `celery_app.send_task("name", ...)` — the latter ignores `task_always_eager` entirely (confirmed: logs `AlwaysEagerIgnored` and actually posts to a broker nothing is consuming), which would silently break the whole eager-mode dev/test/CI path. `backend/worker/tasks.py` keeps `audio_service`'s import lazy (inside each task's function body) specifically so the API process importing this module for `.delay()` stays cheap despite that.

**Ordering under a worker pool** — a real risk once chunks can complete out of order (different workers, different completion times): `SessionRecord.chunk_results` (JSON, keyed by chunk index) is the source of truth; `session_service.materialize_transcript()` rebuilds `transcript_text`/`transcript_segments` from the longest *contiguous* prefix starting at index 0, so a chunk landing early never makes text appear out of order in a live transcript, and duration/latency (order-independent sums) still count every completed chunk regardless. Dedicated tests in `tests/test_tasks.py`.

**Auth** — JWT (PyJWT) + `OAuth2PasswordBearer`, FastAPI's own documented pattern. `bcrypt` directly, NOT passlib's `CryptContext` — confirmed passlib 1.7.4 (unmaintained) raises `AttributeError: module 'bcrypt' has no attribute '__about__'` against the bcrypt version this project installs. New `users` table; `sessions`/`teacher_enrollments` gained `owner_id`. WS auth is `?token=` (browser WebSocket API can't set headers).

**DB** — Postgres via Alembic (`backend/database/migrations/`), hand-written initial migration (no live Postgres in this dev sandbox *at the time it was written* — since verified: PostgreSQL 17 installed natively and the migration run against it directly, `upgrade head` → `downgrade base` → `upgrade head` again, clean). SQLite stays the default when `DATABASE_URL` is unset, so local dev/`pytest` still need no infra.

**Observability** — stdlib `logging` + JSON formatter, no new dependency, split across two files on purpose: `backend/core/logging.py` (`configure_logging()`/`get_logger()`, deliberately starlette-free) is shared by both tiers, `backend/core/request_context.py` (the request-ID contextvar + HTTP middleware, genuinely needs starlette) is API-only. A naive single-file version was caught and fixed: it would have made the worker image import starlette at runtime despite `requirements-worker.txt` never installing it — worker's own startup diagnostics (model load failures) now go through the shared structured logger too, not `print()`. `prometheus-fastapi-instrumentator` on `/metrics`. Optional Sentry via `SENTRY_DSN` (no-op unset).

**Rate limiting** — `slowapi` on `/auth/login`, `/transcribe`, `/teachers/enroll` — confirmed live (12 rapid `/auth/login` calls: first 10 returned `401`, 11th and 12th returned `429`). `MaxUploadSizeMiddleware` rejects an oversized `Content-Length` before the body is read.

**Privacy (RA 10173 basics)** — `consent_confirmed: bool` required at session creation (refused otherwise); `DELETE /sessions/{id}` full purge. Raw audio was already never persisted past processing (temp files cleaned up in `finally` blocks, both in the old single-process design and the new task-based one) — that's now called out explicitly as a privacy property.

**Containerization/CI** — `deployment/Dockerfile.api` (lean: `requirements-api.txt` only, no ffmpeg) + `deployment/Dockerfile.worker` (`requirements-worker.txt`, has ffmpeg) + `deployment/docker-compose.yml` (postgres, redis, api, worker, a `migrate` one-shot service, a shared temp volume for `POST /transcribe`'s whole-file path). `.github/workflows/ci.yml` runs the full suite against real postgres+redis service containers — **run for real** on GitHub's infrastructure (green, merged to `main`), not just written to spec. The Docker *images themselves* are still unbuilt — no Docker installed in this dev sandbox — but the Postgres/Redis/worker-split behavior they'd wrap has been proven directly (native installs, not containers) with real infra, and CI's service containers are themselves real Docker usage, just not of these specific Dockerfiles.

**Known, documented gaps, not oversights**: `POST /transcribe`'s whole-file task takes a filesystem path (assumes API/worker share a volume) rather than base64 bytes like WS chunks do — a full lecture recording is too large to comfortably embed in a broker message; the properly distributed fix is object storage (S3-compatible), left for when real infra exists to build it against. Eager mode's *first* request after a cold start pays the full one-time model-loading cost synchronously and can trip a WS client's keepalive timeout (observed directly in testing) — a real deployment's worker pre-loads models before serving traffic and never blocks the API's event loop regardless, which is the actual point of the split.

---

## Flutter Client (Built)

Lives at `android/` (repo root — see "Repo Structure" above; Flutter's own generated native Android glue folder nests inside as `android/android/`, an accepted cosmetic quirk of that layout choice, not a mistake). All six required screens (see "Flutter Screens (Required)") are built against the real backend contract, not a mock — verified via a real end-to-end run on an Android emulator (Pixel_7 AVD, API 37) against the actual FastAPI + Celery + Postgres + Redis stack running on this same dev machine, not just `flutter analyze`/`flutter test` passing in isolation.

- **`lib/core/`** — `api_client.dart` (one method per `backend/api/*.py` endpoint, throws `ApiException`, global 401 → `AuthController.forceLogout()`), `ws_transcribe_client.dart` (drives `/ws/transcribe`'s start/chunk/end/session_ended protocol), `auth_controller.dart`, `settings_controller.dart` (server URL + `PipelineOptions`, persisted via `shared_preferences`), `secure_storage.dart` (JWT only, via `flutter_secure_storage`), `wav_encoder.dart` + `pcm_chunker.dart` (wrap `record` package's headerless PCM16 stream into self-contained WAV chunks per `chunk_duration_seconds` — required because the WS contract needs each binary frame to be a complete WAV file FFmpeg can parse, and `record`'s `startStream()` only emits headerless PCM), `local_vad.dart` (on-device energy-based VAD pre-filter, round 5 below — `PcmChunker` gates on it before a chunk ever reaches the WS), `polling.dart` (`pollUntil()`, exponential backoff, used for both whole-file-session and teacher-enrollment status polling).
- **`lib/models/`** — `pipeline_config.dart` (`Preset.{fast,balanced,accurate}` → `PipelineOptions`, field names matching `backend/schemas/pipeline.py` exactly; `balanced` matches that schema's own defaults), plus `fromJson`/`toJson` models mirroring every other `backend/schemas/` file.
- **`lib/screens/`** — `auth/` (login/register), `home/` (session library), `enrollment/` (teacher voice enrollment), `recording/` (live recording + subtitles), `transcript/` (search + highlight, client-side substring matching per the backend's "no search endpoint" contract), `minutes/` (structured minutes + export via `share_plus`), `settings/` (server URL, preset selector, advanced panel with outcome-framed labels never raw parameter names, logout).
- **Tests** (`android/test/`, 69 passing) — pure-Dart unit tests for every piece of logic that doesn't need a device: `pipeline_config_test.dart` (preset values + exact `toJson()` key names — the single highest-risk typo surface in the app), `wav_encoder_test.dart` (RIFF/WAVE/fmt/data header correctness), `pcm_chunker_test.dart` (chunk sizing, remainder-carry, flush, VAD gating + hangover sequence), `local_vad_test.dart` (RMS correctness, threshold boundary, windowing catches a short burst a whole-buffer average would miss), model `fromJson` parsing against literal fixtures (including missing-optional-field cases), `ws_messages_test.dart`, `polling_test.dart`, `api_client_test.dart` (round 8), plus two widget tests added while bug-hunting: `app_auth_gate_test.dart` (the app-wide auth gate had zero coverage) and `home_screen_test.dart` (a real crash — see "Resolved this pass, round 11" below).
- **CI** — `.github/workflows/ci.yml` gained a second `flutter` job (`flutter pub get && flutter analyze && flutter test`), pinned to the exact Flutter version this was built against rather than floating `stable`.

**Verified for real, on-device, this session** (not just unit tests): register → login (JWT persists across app restart, confirmed by killing and relaunching the app) → teacher voice enrollment (real mic recording via `record`, real multipart upload, real SpeechBrain embedding extraction via the Celery worker, real `pollUntil()` backoff visible in the request log, ends in a green "Ready" badge) → live recording (`WS /ws/transcribe`, real mic streaming, ~2 dozen chunks actually processed by the worker over several minutes without dropping the connection) → stop → session finalizes server-side (`status: "completed"`) → Transcript screen loads the real session. Settings screen's preset/slider values were confirmed to exactly reflect `PipelinePresets.balanced` (beam 5, chunk 3s) as rendered on-screen, not just in code.

**One real bug found and fixed by this on-device run, not by the unit tests**: the WS's `onDone` handler fired on the *graceful* closure that follows a successful `session_ended` (the server closes the socket right after sending it), racing the screen's own navigation to the Transcript screen and occasionally popping back over it — `_wsClient.close()` is now called (marking the closure as intentional) the moment `session_ended` arrives, before navigating. This is exactly the kind of timing bug unit tests over pure logic can't catch; only running the real WS round-trip against the real backend surfaced it.

**Resolved this pass, round 5** (closing the specific hybrid-architecture gap flagged right after the client build — see "Hybrid Edge/Server Design" above): on-device energy-based VAD (`android/lib/core/local_vad.dart`) — the client now decides locally, before an outgoing chunk is ever sent over the WS, whether it plausibly contains speech, with a 1-chunk hangover so real speech trailing across a chunk boundary isn't clipped. Verified both by 9 new unit tests and by a fresh real on-device run (see below) confirming the gating doesn't hang or misbehave even when literally every chunk is silence — the adversarial case, and exactly what the emulator's mic produces. Noise suppression and offline-fallback recording remain explicitly open, not attempted this pass — see "Hybrid Edge/Server Design" for why.

**Known gaps, not oversights**:
- Tested on the Android **emulator**, not a physical device — real classroom deployment needs a phone on the same Wi-Fi as the backend, which the Settings screen's editable server-address field supports (`10.0.2.2` is emulator-only; a physical device needs the host's real LAN IP) but which hasn't itself been exercised.
- The emulator's virtual microphone is silent, so no real classroom audio has been transcribed through the client yet. Both the server pipeline's VAD and the client's own `LocalVad` (added round 5, below) correctly treat this as "no speech" rather than hallucinating — but this also means an emulator run now sends far fewer chunks to the server than the pre-VAD build did (typically just the hangover-guaranteed first chunk of a session), a real wire-behavior change, not just an internal one. Transcription accuracy on real speech through the *client* (as opposed to through `scripts/`, already covered by backend tests) remains unverified.
- "Import audio file" (`POST /transcribe`'s whole-file path) has no UI — deliberately descoped, not one of the six required screens; noted in `docs/future_ideas.md`.
- The Minutes screen with real (non-empty) content, and transcript search/highlight against real multi-segment text, were code-reviewed but not exercised on-device this session (no session with actual detected speech existed yet to view). Session list swipe-to-delete is the one exception: it was never exercised on-device either, but the bug-hunting pass gave it real automated coverage instead — `android/test/home_screen_test.dart` (round 11) drives the actual swipe/confirm/delete gesture in a widget test and caught a genuine crash (a failed delete poisoning the list on the next reload) no amount of on-device poking without deliberately failing the network call would have surfaced.

---

## Current Build Priority — superseded, see below

The original 14-day sprint list (items 1–4, 8, 9, 11) is done — see "Backend (Built)" and the "Resolved this pass" rounds above (now eleven of them: round 4 closed the last real feature gaps against the thesis's specific objectives; rounds 5–11 are review/bug-hunt/hardening passes — real bugs found and fixed against a genuinely running stack, not new scope). The Flutter client is built too — see "Flutter Client (Built)" below. An operator's runbook (build/run/test/fine-tune/package/hybrid-deploy, all in one place) also exists as a published Claude artifact from this same line of work — regenerate or update it via the `artifact-design`/`artifact-diagramming` skills if asked for one and it isn't already linked in the conversation. Everything genuinely still open from here is either Nathan's own work or blocked on real-world data/people, not more code:

- **Ethics/consent clearance** — Nathan's, blocks all real classroom recording.
- **Real classroom data collection** (Nathan + Andrei + Dan Joseph) — blocks everything below.
- **Fine-tuning run** — `ai/finetuning/` is a tested, ready scaffold with zero trained checkpoints; needs the corpus above.
- **Real evaluation numbers** (WER, teacher-ID, latency for the manuscript) — `evaluation/` scripts are built and tested; zero real results exist, needs real reference transcripts + labeled speaker data.
- **Usability study (SUS)** — `evaluation/sus.py` is scoring math only; the Flutter app itself is now built and emulator-verified, but the study needs it on a physical device and real respondents to actually use it. "Perceived usefulness"/"perceived comprehension support" also have no instrument built yet — needs its own survey items beyond generic SUS.
- **Docker containers actually built and run** — Dockerfiles/compose written and CI-exercises the same infra shape, but no container from these specific files has been built; optional unless deploying past the thesis.
- **Object storage** for `POST /transcribe`'s whole-file path across separate machines — only matters for a true multi-host deployment.

---

*Last updated: September 2026. Maintained by Nathan (PM) + Claude (implementer).*
