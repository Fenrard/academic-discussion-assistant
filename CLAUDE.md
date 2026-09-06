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
| 5. Technical evaluation (accuracy, teacher-ID, latency) | Instrumentation complete and proven (`evaluation/`) | The evaluation itself — real numbers for the manuscript — is unrun |
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
| Noise suppression | `pyrnnoise` library (48kHz round-trip via FFmpeg) |
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
    → pyrnnoise denoising (48kHz round-trip) [enable_denoise toggle]
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
- `enable_denoise` — pyrnnoise denoising (opt-in, off by default)
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
├── ai/                       # Reusable AI modules (source code only)
│   ├── whisper/
│   ├── rnnoise/
│   ├── silero/
│   ├── pyannote/
│   ├── speechbrain/
│   └── finetuning/
├── models/                   # Trained weights/embeddings only (NO source code)
├── datasets/
│   ├── raw/
│   ├── clean/
│   ├── processed/
│   └── metadata/
├── recordings/
├── transcripts/
├── experiments/              # Per-experiment folders for thesis results
├── evaluation/
│   ├── wer/
│   ├── cer/
│   ├── latency/
│   ├── reports/
│   └── plots/
├── docs/                     # DFD.md (Level 0 + Level 1 data flow diagrams), DevelopmentLog.md, future_ideas.md
├── scripts/                  # Dev utilities only, NOT app code
├── tests/
└── deployment/               # Future / Docker
```

**.gitignore must include:** `android/.idea/`
**`license/`** must be a root-level file, not a folder.

---

## Six Built Scripts in `scripts/`

These are dev utilities. Their logic gets promoted into `backend/services/` — not the scripts themselves.

1. `record_test_audio.py` — mic capture → `recordings/classroom.wav` (16000 Hz mono int16)
2. `preprocess_audio.py` — FFmpeg standardization (16kHz mono PCM WAV, loudnorm)
3. `transcribe_audio.py` — Faster-Whisper `small`, int8 CPU, shared `load_model()`
4. `process_pipeline.py` — full pipeline orchestrator with toggle flags; `merge_transcript_with_speakers()` built
5. `simulate_streaming.py` — chunks file into 1–10s pieces (default 3s); full pipeline per chunk
6. `diarize_audio.py` — standalone pyannote pipeline; maps raw labels to Speaker A/B/C by first-appearance

**`process_pipeline.py` logic → `backend/services/audio_service.py`** is the first major backend build task.

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
Android → FastAPI → Audio Service → RNNoise → Silero → Whisper
→ Diarization → Teacher Verification → Database → JSON → Android
```

(Whisper before Diarization before Teacher Verification — see "Pipeline Order (Locked)" above for why that order is structural, not arbitrary.)

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
- If local pipeline too slow: push diarization/verification to server path, keep VAD+RNNoise local — the VAD half of this is now real; the RNNoise half remains the open half

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
- **Memurai (Redis-compatible):** installed natively (Windows service `Memurai`, auto-starts) at `redis://localhost:6379/0` — set `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND`/`REDIS_URL` to it to run a real separate worker (`celery -A backend.worker.celery_app worker --pool=solo` — `--pool=solo` is required on Windows, prefork needs fork()). Also optional — no broker configured means Celery's eager mode runs tasks inline in the API process.
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

### RNNoise — actual implementation
- Uses `pyrnnoise` library, **NOT** FFmpeg `arnndn` filter — this is a deliberate deviation from the manuscript's own Software Stack section, which describes RNNoise "applied through FFmpeg's arnndn filter." See `docs/paper-vs-implementation.md` for why `pyrnnoise` was kept over `arnndn` and what to change in the manuscript text.
- Requires a 48kHz round-trip: upsample (ffmpeg) → `RNNoise.denoise_wav()` → downsample back to 16kHz (ffmpeg)
- `RNNOISE_SAMPLE_RATE = 48000`, `SAMPLE_RATE = 16000`
- Two temp files created (`_48k.wav`, `_48k_denoised.wav`) and cleaned up after
- `pyrnnoise` must be installed: `pip install pyrnnoise`
- `enable_denoise=False` (default) — opt-in, not opt-out

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
- `--denoise` — enable RNNoise (off by default)
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

- Flutter WebSocket integration: **built and verified end-to-end on an Android emulator** — see "Flutter Client (Built)" below. Real physical-device testing (as opposed to emulator) is still open.
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
- No load testing has been done — the worker-pool/async rearchitecture is correct-by-construction and unit/integration tested under real Postgres+Redis, but its actual throughput under concurrent load is unmeasured
- Docker images themselves (not just CI's postgres/redis service containers) have never been built and run as actual containers — `deployment/docker-compose.yml` is written to spec and CI-adjacent-verified only

**Resolved this pass** (were unbuilt, now built — see "Backend (Built)" below): SpeechBrain ECAPA teacher verification, FastAPI endpoints (POST + WebSocket), transcript persistence, glossary post-processing, TextRank + rule-based minutes, `evaluation/wer.py` + `evaluation/latency.py`.

**Resolved this pass, round 2** (beyond the 14-day list, rest of CLAUDE.md's "Evaluation Metrics (Complete)"): `evaluation/teacher_id.py` (precision/recall/F1, FAR/FRR), `evaluation/sus.py` (SUS scoring), `evaluation/resources.py` (CPU/memory via psutil), and the `ai/finetuning/` LoRA/PEFT scaffold (train + merge/convert-to-CTranslate2) for the "Non-Negotiable" fine-tuning item.

**Resolved this pass, round 3** (production/market-deployment architecture — see "Production Architecture" below): the blocking-event-loop bug (API/worker split via Celery), auth (JWT), Postgres + Alembic migrations, structured logging + Prometheus metrics + optional Sentry, rate limiting + upload-size limits, API versioning (`/api/v1`), consent/deletion (RA 10173 basics), Docker images + docker-compose + CI. Verified for real, not just written to spec: PostgreSQL 17 and a Redis-compatible server (Memurai) installed natively, the Alembic migration run against real Postgres, a genuinely separate worker process proven non-blocking against real Redis, and a green `.github/workflows/ci.yml` run on GitHub's own infrastructure (merged to `main`). Two real bugs were caught only by this — `celery_app.send_task()` silently ignoring eager mode, and the worker process never importing the `User` model (broke the `sessions.owner_id` foreign key outside the single-process path) — both fixed and covered by the merged commit.

**Resolved this pass, round 4** (closing two gaps between the code and the thesis's actual specific objectives): teacher-voice **prioritization**, not just identification — `keyword_service.build_weighted_text()` weights teacher-labeled speech more heavily into TextRank, `minutes_service.py`'s key-point selection and topic labeling both rank teacher segments first, and `teacher_speech_ratio`/`teacher_speakers` are new minutes fields. Also **definitions** extraction (heuristic trilingual pattern matching), the previously-missing fourth item from "key points, topics, definitions, and tasks." Both are no-ops when `enable_teacher_verification` was off, so nothing existing changed behavior.

**Round 3 — production/market-deployment rearchitecture** (explicit scope change past CLAUDE.md's original "no production scaling" boundary, at the user's request after an architecture review): see "Production Architecture" below. This is a real rearchitecture, not additive — `backend/main.py` no longer loads any ML models, `POST /transcribe` is now async (202 + poll), and every route requires auth. The bullets right below this describe the CURRENT shape; treat mentions of "SQLite" or "synchronous" pipeline calls elsewhere in this file as historical unless a bullet here says otherwise.

---

## Backend (Built)

Everything below lives in `backend/` and `evaluation/`, promoted from the six scripts per CLAUDE.md's rule (scripts themselves untouched).

- **`backend/services/audio_service.py`** — the pipeline orchestrator, unchanged by the Round 3 rearchitecture (only *what calls it* changed — see "Production Architecture"). Adds one thing `process_pipeline.py` never actually did: FFmpeg preprocessing now runs unconditionally on every chunk/file (`ingest_audio()`), closing the gap between the locked "always on" rule and what the script actually executed. Denoise/VAD/diarization/teacher-verification stay independently toggleable. Per-stage latency recorded on every call.
- **`backend/services/teacher_verification_service.py`** — SpeechBrain ECAPA-TDNN (`spkrec-ecapa-voxceleb`), cosine similarity against enrolled embeddings, lazy-imported the same way `pyrnnoise` already was so a missing install degrades gracefully instead of crashing the worker. Labels each segment `is_teacher`/`teacher_name`/`confidence` — the *identification* half of "teacher voice-prioritized"; `keyword_service.py`/`minutes_service.py` below are the *prioritization* half.
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
- **Tests** (`android/test/`, 57 passing) — pure-Dart unit tests for every piece of logic that doesn't need a device: `pipeline_config_test.dart` (preset values + exact `toJson()` key names — the single highest-risk typo surface in the app), `wav_encoder_test.dart` (RIFF/WAVE/fmt/data header correctness), `pcm_chunker_test.dart` (chunk sizing, remainder-carry, flush, VAD gating + hangover sequence), `local_vad_test.dart` (RMS correctness, threshold boundary, windowing catches a short burst a whole-buffer average would miss), model `fromJson` parsing against literal fixtures (including missing-optional-field cases), `ws_messages_test.dart`, `polling_test.dart`.
- **CI** — `.github/workflows/ci.yml` gained a second `flutter` job (`flutter pub get && flutter analyze && flutter test`), pinned to the exact Flutter version this was built against rather than floating `stable`.

**Verified for real, on-device, this session** (not just unit tests): register → login (JWT persists across app restart, confirmed by killing and relaunching the app) → teacher voice enrollment (real mic recording via `record`, real multipart upload, real SpeechBrain embedding extraction via the Celery worker, real `pollUntil()` backoff visible in the request log, ends in a green "Ready" badge) → live recording (`WS /ws/transcribe`, real mic streaming, ~2 dozen chunks actually processed by the worker over several minutes without dropping the connection) → stop → session finalizes server-side (`status: "completed"`) → Transcript screen loads the real session. Settings screen's preset/slider values were confirmed to exactly reflect `PipelinePresets.balanced` (beam 5, chunk 3s) as rendered on-screen, not just in code.

**One real bug found and fixed by this on-device run, not by the unit tests**: the WS's `onDone` handler fired on the *graceful* closure that follows a successful `session_ended` (the server closes the socket right after sending it), racing the screen's own navigation to the Transcript screen and occasionally popping back over it — `_wsClient.close()` is now called (marking the closure as intentional) the moment `session_ended` arrives, before navigating. This is exactly the kind of timing bug unit tests over pure logic can't catch; only running the real WS round-trip against the real backend surfaced it.

**Resolved this pass, round 5** (closing the specific hybrid-architecture gap flagged right after the client build — see "Hybrid Edge/Server Design" above): on-device energy-based VAD (`android/lib/core/local_vad.dart`) — the client now decides locally, before an outgoing chunk is ever sent over the WS, whether it plausibly contains speech, with a 1-chunk hangover so real speech trailing across a chunk boundary isn't clipped. Verified both by 9 new unit tests and by a fresh real on-device run (see below) confirming the gating doesn't hang or misbehave even when literally every chunk is silence — the adversarial case, and exactly what the emulator's mic produces. Noise suppression and offline-fallback recording remain explicitly open, not attempted this pass — see "Hybrid Edge/Server Design" for why.

**Known gaps, not oversights**:
- Tested on the Android **emulator**, not a physical device — real classroom deployment needs a phone on the same Wi-Fi as the backend, which the Settings screen's editable server-address field supports (`10.0.2.2` is emulator-only; a physical device needs the host's real LAN IP) but which hasn't itself been exercised.
- The emulator's virtual microphone is silent, so no real classroom audio has been transcribed through the client yet. Both the server pipeline's VAD and the client's own `LocalVad` (added round 5, below) correctly treat this as "no speech" rather than hallucinating — but this also means an emulator run now sends far fewer chunks to the server than the pre-VAD build did (typically just the hangover-guaranteed first chunk of a session), a real wire-behavior change, not just an internal one. Transcription accuracy on real speech through the *client* (as opposed to through `scripts/`, already covered by backend tests) remains unverified.
- "Import audio file" (`POST /transcribe`'s whole-file path) has no UI — deliberately descoped, not one of the six required screens; noted in `docs/future_ideas.md`.
- Session list swipe-to-delete, the Minutes screen with real (non-empty) content, and transcript search/highlight against real multi-segment text were code-reviewed but not exercised on-device this session (no session with actual detected speech existed yet to view).

---

## Current Build Priority — superseded, see below

The original 14-day sprint list (items 1–4, 8, 9, 11) is done — see "Backend (Built)" and the four "Resolved this pass" rounds above. **All backend/code work is done as of round 4. The Flutter client is now built too — see "Flutter Client (Built)" below.** Everything genuinely still open from here is either Nathan's own work or blocked on real-world data/people, not more code:

- **Ethics/consent clearance** — Nathan's, blocks all real classroom recording.
- **Real classroom data collection** (Nathan + Andrei + Dan Joseph) — blocks everything below.
- **Fine-tuning run** — `ai/finetuning/` is a tested, ready scaffold with zero trained checkpoints; needs the corpus above.
- **Real evaluation numbers** (WER, teacher-ID, latency for the manuscript) — `evaluation/` scripts are built and tested; zero real results exist, needs real reference transcripts + labeled speaker data.
- **Usability study (SUS)** — `evaluation/sus.py` is scoring math only; needs the finished Flutter app + real respondents. "Perceived usefulness"/"perceived comprehension support" also have no instrument built yet — needs its own survey items beyond generic SUS.
- **Docker containers actually built and run** — Dockerfiles/compose written and CI-exercises the same infra shape, but no container from these specific files has been built; optional unless deploying past the thesis.
- **Object storage** for `POST /transcribe`'s whole-file path across separate machines — only matters for a true multi-host deployment.

---

*Last updated: September 2026. Maintained by Nathan (PM) + Claude (implementer).*
