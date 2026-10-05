# AI/ML Pipeline — Complete Reference

> Written 2026-09-15. Model versions confirmed via `pip freeze` in this repo's own `.venv`, run
> this pass. Performance numbers below are carried from this project's own prior measurements
> (`CLAUDE.md` Part 2, round 8) — they are real measurements on this project's own dev hardware,
> not vendor benchmarks, and are labeled as such throughout. Anything not directly measured is
> marked **UNKNOWN — needs empirical measurement**, per the accuracy rule this whole doc set
> follows.

## The pipeline, stage by stage

```
Audio (any supported format, any sample rate/channel count)
  → ingest_audio()        FFmpeg: -ar 16000 -ac 1 -c:a pcm_s16le -af loudnorm     [ALWAYS ON]
  → clean_audio()         FFmpeg: -af afftdn=nr=12:nf=-25:tn=1                     [toggle, OFF by default]
  → detect_speech()       Silero VAD: get_speech_timestamps()                      [toggle, ON by default]
  → transcribe_audio()    Faster-Whisper: WhisperModel.transcribe() per VAD span,
                           then glossary.apply() per resulting segment
  → diarize_audio()       pyannote.audio Pipeline, optional                        [toggle, OFF by default, needs HF_TOKEN]
  → apply_teacher_verification()   SpeechBrain ECAPA + cosine similarity           [toggle]
  → (at session finalize, not per chunk) extract_keywords() + generate_minutes()
```

## Model-by-model reference

### 1. Faster-Whisper (speech-to-text) — the core function of the app

- **Model name / source:** `openai/whisper-small` weights, run through CTranslate2 via the
  `faster-whisper` Python package (installed version: **1.2.1**; CTranslate2: **4.8.1**).
- **Exact identifier used:** `settings.whisper_model_size` = `"small"` by default
  (`WHISPER_MODEL_SIZE` env var) — `faster-whisper` resolves this to a Hugging Face-hosted
  CTranslate2-converted version of `openai/whisper-small` on first use, caching it locally.
- **Purpose:** transcribes speech to text.
- **Input:** a mono float32 waveform at 16kHz (a slice of the standardized audio, bounded by one
  VAD-detected speech span).
- **Output:** one or more `Segment` objects per call (`start`, `end`, `text`, `avg_logprob`,
  `no_speech_prob`), plus a detected `language`/`language_probability` for that call.
- **Language support:** multilingual, no language forced — auto-detected per call
  (`model.transcribe(clip, beam_size=beam_size)`, no `language=` argument). Whisper's original
  pretraining covers ~99 languages including Filipino/Tagalog and English; **Hiligaynon has no
  dedicated token** — the model treats it as an unrecognized language and typically resolves it
  phonetically toward Filipino/Tagalog. This is exactly the gap the planned LoRA fine-tuning
  (below) exists to narrow.
- **CPU/GPU:** CPU in this codebase (`WHISPER_DEVICE` defaults to `"cpu"`; it's the one model in
  this codebase with an actual device-selection env var, but it has never been exercised with
  anything other than `"cpu"` — all measured numbers are CPU numbers). `WHISPER_COMPUTE_TYPE`
  defaults to `"int8"` (quantized).
- **VRAM:** N/A on this CPU-only path. **UNKNOWN — needs empirical measurement** if a CUDA build
  were ever installed and `WHISPER_DEVICE=cuda` set.
- **Where loaded:** `backend/services/audio_service.py: load_whisper_model()`, called once by
  `backend/worker/celery_app.py: _load_models()` at worker-process startup.
- **Where called:** `backend/services/audio_service.py: transcribe_audio()`.
- **Preprocessing:** the always-on FFmpeg standardization + optional denoise + VAD segmentation
  upstream.
- **Postprocessing:** `glossary.apply()` on each segment's text, immediately.
- **Config parameters:** `beam_size` (default 5, user-adjustable 1–10 via the Flutter "Accuracy
  vs. speed" slider — higher = more accurate, slower), `whisper_cpu_threads` (0 = CTranslate2's own
  default; set to the host's physical core count for a single-worker deployment).
- **Status:** **IMPLEMENTED.**

### 2. LoRA/PEFT fine-tuning of Whisper for Hiligaynon

- **Source:** `ai/finetuning/finetune_whisper.py` (uses `transformers` **5.16.1**, `peft`
  **0.20.0**, `accelerate` **1.14.0**, `datasets` **5.0.1**), `ai/finetuning/
  convert_to_faster_whisper.py` (merges the LoRA adapter into the base weights, then converts to
  CTranslate2 format via `ctranslate2`'s converter, bundled with the `faster-whisper` install).
- **Purpose:** adapt Whisper's weights toward this project's specific
  Hiligaynon/Filipino/English code-switching pattern, using a locked 90/10 train/eval split.
- **Input:** a HuggingFace `datasets.Dataset` with `audio` (16kHz WAV) and `text` (ground-truth
  transcript, code-switching left exactly as spoken — not normalized away) columns, expected at
  `datasets/processed/<corpus_name>`.
- **Output:** a LoRA adapter directory, then (after conversion) a CTranslate2 directory that
  `WhisperModel(...)` can load in place of a model name via `WHISPER_MODEL_SIZE`.
- **Status:** **PLANNED / NOT IMPLEMENTED.** The scripts import cleanly and are covered by their
  own error-path tests, but **have never been run against real data** — `datasets/processed/`
  contains only a `.gitkeep` file, confirmed this pass. No trained checkpoint exists anywhere in
  this repository or its gitignored `models/` folder (that folder currently holds only the
  SpeechBrain ECAPA checkpoint, confirmed this pass — no Whisper checkpoint).
- **GPU requirement for actually running this:** the scripts are written to run on Google Colab's
  free GPU tier, not on local hardware — no local CUDA setup is required *for this specific step*
  even if the rest of the app never touches GPU locally.

### 3. Silero VAD (voice activity detection)

- **Source:** the `silero-vad` PyPI package, installed version **6.2.1**.
- **Purpose:** finds precise speech-span boundaries within a standardized audio chunk, so Whisper
  only transcribes speech, not silence/noise gaps.
- **Input:** a mono float32 waveform at 16kHz.
- **Output:** a list of `{start, end}` sample-index timestamps (one per detected speech span).
- **Language support:** language-agnostic (it detects speech vs. non-speech, not what language the
  speech is in).
- **CPU/GPU:** CPU only in this codebase — no device parameter exists anywhere for this model.
- **Where loaded:** `load_silero_vad()`, called once by `_load_models()`.
- **Where called:** `backend/services/audio_service.py: detect_speech()`.
- **Config parameters:** none exposed beyond the `enable_vad` toggle itself — Silero's own internal
  thresholds are left at their library defaults; no `SILERO_THRESHOLD`-style env var exists in this
  codebase.
- **Note on a genuine Windows-specific quirk, reproduced this pass:** `silero_vad.model`'s
  `read_audio()` helper pulls in `torch`/`torchaudio`'s optional `torchcodec` backend, which failed
  to load its native DLL on this exact machine during this pass's `pytest` run (`OSError: Could not
  load this library: ...torchcodec\libtorchcodec_core8.dll`, tried versions 4 through 8, all
  failed) — **this is why `audio_service.py: load_waveform()` deliberately uses `soundfile.read()`
  instead of Silero's own `read_audio()`.** The torchcodec failure is non-fatal precisely because
  of that workaround — confirmed this pass: the full test suite still passed 90/1 despite the
  warning appearing in the log. See `docs/TROUBLESHOOTING.md`.
- **Status:** **IMPLEMENTED.**

### 4. On-device VAD (Flutter) — NOT the same model as Silero

- **Source:** hand-written, `android/lib/core/local_vad.dart` — a plain RMS energy calculation,
  **not a machine-learning model at all**, deliberately (a learned model was judged unnecessary
  complexity for a binary "does this chunk plausibly contain speech" gate at near-zero compute
  cost).
- **Purpose:** decide, on the phone, before a chunk is ever transmitted, whether it's worth sending
  — a bandwidth/relevance filter, not a transcription-quality filter (the server's Silero VAD still
  runs on whatever does arrive).
- **Threshold:** `0.01` normalized RMS (~-40 dBFS) — an explicitly unvalidated heuristic default,
  the class's own doc comment says so directly.
- **Status:** **IMPLEMENTED**, deliberately not a model.

### 5. pyannote.audio (speaker diarization) — optional

- **Model identifier:** `pyannote/speaker-diarization-community-1` (a gated Hugging Face model —
  requires accepting its terms on huggingface.co and a valid `HF_TOKEN`).
- **Source:** `pyannote.audio` PyPI package, installed version **4.0.7**.
- **Purpose:** clusters speech into generic "Speaker A/B/C..." turns, independent of any known
  identity.
- **Input:** a full audio file path (not a waveform array — pyannote's pipeline reads the file
  itself).
- **Output:** a `DiarizeOutput` dataclass whose `.speaker_diarization` is a pyannote `Annotation`;
  iterated via `.itertracks(yield_label=True)` to get `(Segment, track, label)` triples, then mapped
  to `"Speaker A"/"Speaker B"...` by first-appearance order (`format_speaker_segments()`).
- **CPU/GPU:** CPU only in this codebase — no device argument passed to `Pipeline.from_pretrained()`
  anywhere.
- **Where loaded:** `load_diarization_model()`, called once by `_load_models()` **only if
  `HF_TOKEN` is set** — otherwise diarization is silently unavailable (logged, not an error) for
  that worker process's lifetime.
- **Config parameters:** `num_speakers` (optional exact count, passed through if the user provides
  one in the Flutter Advanced Settings panel; otherwise pyannote auto-detects the count).
- **Status:** **IMPLEMENTED**, optional, off by default. **Untested this pass** — no `HF_TOKEN` was
  configured in this environment, so this code path did not execute during this pass's validation
  run; it is covered by `tests/test_tasks.py`'s mocked paths and by the fix history in `CLAUDE.md`
  Part 2 round 9 (a real, previously-shipped `AttributeError` on every genuine diarization run,
  since fixed), but a live end-to-end diarization call was not re-verified in this specific pass.

### 6. SpeechBrain ECAPA-TDNN (teacher voice verification)

- **Model identifier:** `speechbrain/spkrec-ecapa-voxceleb`.
- **Source:** `speechbrain` PyPI package, installed version **1.1.1**.
- **Purpose:** extracts a fixed-length speaker-embedding vector from a short audio clip; a second
  clip's embedding is compared to a stored enrollment embedding by cosine similarity to decide
  "is this the enrolled teacher."
- **Input:** a mono float32 waveform at 16kHz (the enrollment sample, or a slice of a transcript
  segment).
- **Output:** an embedding vector (ECAPA-TDNN's standard architecture output is 192-dimensional),
  returned as a plain `list[float]` for JSON storage.
- **Pretraining data:** VoxCeleb1+2 (~7,000+ speakers, YouTube interview audio) — **not**
  Hiligaynon/Filipino/English classroom speech, and **not** fine-tuned in this project at all;
  applied zero-shot. This is exactly why `teacher_verification_threshold` is documented everywhere
  in this codebase as an unvalidated default.
- **CPU/GPU:** CPU only — `EncoderClassifier.from_hparams()` is called with no `run_opts={"device":
  "cuda"}` anywhere in this codebase.
- **Where loaded:** `load_verification_model()`, called once by `_load_models()`.
- **Where called:** `extract_embedding()` (enrollment) and `verify_segment()` (per-segment
  comparison during transcription), both in `backend/services/teacher_verification_service.py`.
- **Config parameters:** `teacher_verification_threshold` (default `0.35`, `TEACHER_
  VERIFICATION_THRESHOLD` env var — a cosine-similarity cutoff near a typical VoxCeleb
  equal-error-rate operating point, not calibrated against this project's own real data). A
  segment shorter than 0.3s is skipped (labeled non-teacher without running the model) — too little
  audio for a reliable embedding.
- **Multi-teacher support:** yes — every enrolled, `ready`-status teacher's embedding is compared,
  best match wins, then the threshold is applied to that best score.
- **Status:** **IMPLEMENTED.**

### 7. FFmpeg `afftdn` (noise suppression) — NOT RNNoise

- **What it is:** FFmpeg's built-in FFT-based adaptive denoise filter — classical DSP, **not a
  machine-learning model at all**.
- **Filter string:** `afftdn=nr=12:nf=-25:tn=1` (`nr`=12 moderate reduction strength; `nf`=-25
  noise floor, raised from FFmpeg's -50dB default since classroom ambient sits above near-silence;
  `tn=1` tracks non-stationary noise through a session rather than locking to the first frame).
  **Explicitly unvalidated heuristic values**, same caveat class as the teacher-verification
  threshold.
- **History:** replaced `pyrnnoise` (a Python wrapper around RNNoise, a genuine neural denoiser)
  after `pyrnnoise` 0.4.3 became permanently uninstallable alongside this project's other
  dependencies on Python 3.11 — see `docs/TROUBLESHOOTING.md`. **If you see any reference to
  RNNoise/`arnndn`/`pyrnnoise` anywhere else in this repo's documentation (including the thesis
  manuscript), it does not describe the current implementation.**
- **Status:** **IMPLEMENTED**, off by default.

### 8. TextRank keyword extraction

- **Not a pretrained model** — a from-scratch implementation of the classic TextRank algorithm
  (Mihalcea & Tarau, 2004) on top of `networkx` **3.6.1**'s PageRank implementation. No external
  API, no transformer model, no `nltk`/`sumy` dependency.
- **Input:** the session's full transcript text (teacher-weighted — see `docs/BACKEND.md`).
- **Output:** up to 10 keyword/keyphrase strings, ranked by score.
- **Status:** **IMPLEMENTED.**

### 9. Rule-based minutes generation

- **Not a model, not an LLM call of any kind.** Silence-gap topic segmentation, regex-pattern
  definition/action-item detection, teacher-prioritized ranking — all deterministic Python. See
  `docs/BACKEND.md` for the full mechanism.
- **Status:** **IMPLEMENTED**, explicitly documented (in its own module docstring) as a heuristic
  that "will miss/misfire on real classroom audio," not an NLP model.

## Performance requirements

All numbers below are this project's own prior measurements on its own dev machine — see
`CLAUDE.md` Part 2, round 8, for the original context. **Every number is a CPU number** — this
codebase has never run any of these models on GPU.

| Metric | Measured value | Conditions |
|---|---|---|
| Cold model load (all models, one worker process) | ~7.5s | Whisper 4.2s + SpeechBrain 2.9s + Silero 0.4s |
| Warm preprocess (FFmpeg standardize) | ~0.26s | 5-second clip |
| Warm denoise (`afftdn`) | ~0.1s | 5-second clip |
| Warm VAD (Silero) | ~0.3s | 5-second clip |
| Warm transcription (Whisper `small`, int8) | ~7–11s | 5-second clip |
| Streaming real-time factor (RTF) | **≈2.4–2.9** | A 3-second chunk takes ~8.6s to fully process on one worker — **slower than real-time** |
| `WHISPER_CPU_THREADS` tuning effect | ~17% faster single-stream | Set to physical core count (8 cores: 8.4s → 7.0s for a 5s clip); regresses past core count; leave at 0 (auto) under a multi-worker pool |
| Concurrency correctness | 6 parallel WS sessions × 3 chunks each, real worker + real Postgres, no lost updates | Round 8 stress test |

**Expected RAM:** **UNKNOWN — needs empirical measurement.** No systematic RAM profiling exists in
this project's history beyond `evaluation/resources.py`'s tooling existing (built, `psutil`-based,
but not run against real data this pass or documented previously with a concrete number).

**Expected VRAM:** N/A currently — nothing runs on GPU. If GPU support were added: **UNKNOWN**,
would need direct measurement; Whisper `small` alone typically needs roughly 1–2GB VRAM for
inference in community reporting, but this project has never measured it and that figure should
not be treated as this project's own verified number.

### Specifically: an RTX 3050 Ti 4GB + 16GB RAM machine

This is close to (not identical to) this project's own actual dev machine (a plain RTX 3050, not
Ti, 4GB VRAM either way, 16GB RAM per the thesis manuscript's Environment section — see
`CLAUDE.md` Part 2's fact-check of that section). Since the installed `torch` build here is
CPU-only, **the GPU would currently sit unused regardless of which RTX 3050 variant is
present** — every number above is what such a machine actually gets, running entirely on CPU. If a
CUDA-enabled torch build were installed and the (currently nonexistent) code changes to pass
`device="cuda"` were made: **UNKNOWN — needs empirical measurement**, but 4GB VRAM is tight for
running Whisper `small` + SpeechBrain + pyannote simultaneously in the same process without careful
memory management (each model would need to be loaded and possibly released rather than all held
in VRAM at once) — this is an engineering judgment call worth surfacing, not a measured fact.

### Bottlenecks / known slow operations

- **Whisper transcription itself** is the dominant cost in every measurement above — by a wide
  margin over every other stage.
- **Teacher verification calls SpeechBrain once per Whisper segment, with no batching** — for a
  typical multi-segment discussion this is 40–60+ sequential CPU forward passes. Documented as a
  real, known, not-yet-addressed cost (`CLAUDE.md` Part 2, round 7's deferred list), not a bug.
- **`materialize_transcript()`/`append_chunk_result()` redo O(n) work on every chunk arrival** —
  fine at chunk counts this project has tested, a real concern for a full lecture-length session
  (hundreds of chunks/hour) — same deferred-list item.

### CPU fallback behavior

There is no separate "CPU fallback" code path to speak of, because CPU **is** the only path this
codebase currently implements — there's nothing to fall back *from*. `WHISPER_DEVICE` is the one
knob that exists and it defaults to `"cpu"` already.
