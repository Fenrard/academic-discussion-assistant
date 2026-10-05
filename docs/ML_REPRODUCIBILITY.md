# ML Reproducibility Audit

> Written 2026-09-18. Every claim below was verified by one of: reading the exact model-loading
> code in `backend/services/*.py` and `backend/worker/celery_app.py`; running `pip freeze` in this
> repo's own `.venv`; directly inspecting this machine's real Hugging Face Hub cache
> (`~/.cache/huggingface/hub/`) and the repo's own gitignored `models/` directory, file by file,
> this pass; and one live log capture from an actual model-loading run earlier this session that
> recorded the exact HTTP request faster-whisper made to Hugging Face Hub. Where a claim is
> **external knowledge** (e.g., a model's publicly known license) rather than something this
> repository's own files/cache prove, it is labeled **INFERRED / EXTERNAL** explicitly. Nothing
> below is guessed silently.

---

## 1. Faster-Whisper (speech-to-text)

- **Model/algorithm name:** Whisper `small`, running through the CTranslate2 inference engine via
  the `faster-whisper` Python package.
- **Exact model identifier:** **`Systran/faster-whisper-small`** — **this is directly observed,
  not inferred.** A live log captured during this project's own work this session recorded the
  literal HTTP request: `GET https://huggingface.co/api/models/Systran/faster-whisper-small/
  revision/main`. This is a CTranslate2-converted mirror of OpenAI's `openai/whisper-small`
  weights, published by the Systran organization specifically for `faster-whisper` consumption —
  **not** a direct download from `openai/whisper-small` itself.
- **Source/repository:** Hugging Face Hub, `https://huggingface.co/Systran/faster-whisper-small`.
- **Version:** Whatever `revision/main` currently resolves to on Hugging Face Hub — this project
  pins no specific commit/revision. Package versions (verified via `pip freeze` this session):
  `faster-whisper==1.2.1`, `ctranslate2==4.8.1`.
- **Framework:** CTranslate2 (a dedicated inference engine, not raw PyTorch, though PyTorch is
  still installed as a shared dependency of the other models in this stack).
- **Python package:** `faster-whisper`.
- **Model download mechanism:** Automatic, on first `WhisperModel(...)` construction — `faster-
  whisper` calls into `huggingface_hub` internally to resolve and cache the named repo. **No
  `download_root` parameter is passed anywhere in this codebase** (confirmed by direct `grep` of
  `backend/services/audio_service.py`), so it uses `huggingface_hub`'s own default cache location.
- **Local model path:** `~/.cache/huggingface/hub/models--Systran--faster-whisper-small/` —
  confirmed present on this machine, **464MB** on disk (`du -sh`, this pass). Not inside the repo
  directory, not gitignored-and-tracked, not anywhere version control ever sees.
- **Initialization code:** `backend/services/audio_service.py: load_whisper_model()` →
  `WhisperModel(settings.whisper_model_size, device=settings.whisper_device, compute_type=
  settings.whisper_compute_type, cpu_threads=settings.whisper_cpu_threads)`. Called exactly once
  per worker process, from `backend/worker/celery_app.py: _load_models()`.
- **Inference code:** `backend/services/audio_service.py: transcribe_audio()` —
  `model.transcribe(clip, beam_size=beam_size)`, called once per Silero-VAD-detected speech span.
- **Input format:** a mono float32 NumPy waveform slice at 16kHz (a `soundfile`-loaded array,
  sliced by sample index).
- **Output format:** an iterator of `Segment` objects (`start`, `end`, `text`, `avg_logprob`,
  `no_speech_prob`) plus one `info` object (`language`, `language_probability`) per call.
- **Preprocessing:** the always-on FFmpeg standardization (`ingest_audio()`) and optional
  `afftdn` denoise upstream; no language is forced (`language=` is never passed).
- **Postprocessing:** `glossary.apply()` runs on each segment's `.text` immediately after
  decoding, inside the same loop.
- **Configuration (env vars, `backend/core/config.py`):** `WHISPER_MODEL_SIZE` (default
  `"small"` — also accepts a local CTranslate2 directory path, the mechanism the planned
  fine-tuned model would use), `WHISPER_DEVICE` (default `"cpu"`), `WHISPER_COMPUTE_TYPE`
  (default `"int8"`), `WHISPER_CPU_THREADS` (default `0`, meaning CTranslate2's own auto-choice).
- **Thresholds:** `beam_size` (default 5, user-adjustable 1–10 from the Flutter app) is the only
  tunable decoding parameter exposed; no confidence-score filtering is applied anywhere to
  Whisper's own `avg_logprob`/`no_speech_prob` fields (they're stored and returned to the client
  but nothing in this codebase acts on them automatically).
- **Device selection / CPU-GPU behavior:** `WHISPER_DEVICE` is the **only** device-selection knob
  that exists anywhere in this codebase, for any model. Default `"cpu"`. **Never exercised as
  anything but `"cpu"`** in this project's history — every latency number ever recorded
  (`docs/ML_PIPELINE.md`) is a CPU number.
- **VRAM implications:** N/A currently (CPU-only). If `WHISPER_DEVICE=cuda` were ever set: the
  installed `torch` build in this exact `.venv` is `2.13.0+cpu` (confirmed by direct execution
  this session, `torch.cuda.is_available()` → `False`) — setting this env var alone would **not**
  make GPU inference work; a CUDA-enabled `torch` reinstall would be required first.
- **Expected model files:** the CTranslate2-converted weight/config/tokenizer files Hugging Face
  Hub serves for `Systran/faster-whisper-small` — confirmed on disk this pass as four content
  blobs plus a `refs/main` pointer and a file tree manifest, totaling 464MB.
- **Authentication requirements:** none — this is a public, non-gated repository.
- **License:** **INFERRED / EXTERNAL** — no `LICENSE`/model-card file is cached locally for this
  repo on this machine (checked this pass — the cache holds only content blobs, no `README.md`).
  Whisper's own weights are publicly documented (outside this repository) as MIT-licensed by
  OpenAI; the Systran conversion's own specific terms were not independently verified from
  anything in this repository or its cache.
- **Pretrained or fine-tuned:** **Pretrained only, currently.** The LoRA/PEFT fine-tuning
  pipeline (§5 below) exists but has never been run — the model actually loaded by this system
  today is the stock, unmodified `Systran/faster-whisper-small` conversion of OpenAI's public
  weights.
- **Local weights exist:** yes, cached on this development machine (464MB, confirmed this pass).
  **Not present on a fresh clone** — this cache directory is outside the repository entirely.
- **Runtime download dependency:** **yes** — a fresh machine with no prior cache will trigger a
  real network download from Hugging Face Hub the first time any pipeline call reaches
  `load_whisper_model()`.
- **Classification: IMPLEMENTED.**

## 2. Silero VAD (voice activity detection)

- **Model/algorithm name:** Silero VAD.
- **Exact model identifier:** shipped as a versioned file bundled inside the `silero-vad` PyPI
  package itself (`.jit`/`.onnx`/`.safetensors` files) — **not** a Hugging Face Hub repo ID at all.
- **Source/repository:** the `silero-vad` package on PyPI, version **6.2.1** (confirmed via `pip
  freeze` this session).
- **Framework:** PyTorch (`.jit`, TorchScript) and/or ONNX Runtime, depending on which internal
  loader path the package uses; both formats are present in the installed package.
- **Model download mechanism:** **none, at runtime.** Directly confirmed this pass: the model
  files (`silero_vad.jit`, `silero_vad.onnx`, `silero_vad_16k.safetensors`,
  `silero_vad_16k_op15.onnx`, `silero_vad_half.onnx`, `silero_vad_op18_ifless.onnx`) are physically
  present inside `.venv/Lib/site-packages/silero_vad/data/` — installed by `pip install` itself,
  as ordinary package data, not fetched separately over the network.
- **Local model path:** `<venv>/Lib/site-packages/silero_vad/data/` — inside the Python
  environment, not the repository, not `~/.cache/huggingface`.
- **Initialization code:** `load_silero_vad()` (the package's own function), called from
  `backend/worker/celery_app.py: _load_models()`, wrapped in a `try/except` — failure is logged
  as a warning, not raised (VAD is one of the "best-effort" optional models at worker startup).
- **Inference code:** `backend/services/audio_service.py: detect_speech()` →
  `get_speech_timestamps(waveform, vad_model, sampling_rate=SAMPLE_RATE)`.
- **Input format:** a `torch.Tensor` (float32) waveform, loaded via `soundfile` — deliberately
  **not** via Silero's own `read_audio()` helper (see below).
- **Output format:** a list of `{start, end}` sample-index dicts.
- **Preprocessing:** none beyond the always-on FFmpeg standardization upstream.
- **Configuration:** `enable_vad` toggle only (`backend/schemas/pipeline.py`); no threshold env
  var exists for Silero's own internal speech-probability cutoff anywhere in this codebase —
  Silero's library defaults are used as-is.
- **Device selection:** CPU only — no device knob exists for this model anywhere.
- **VRAM implications:** none — this model is small enough that CPU inference is the only path
  ever used or considered in this project.
- **Expected model files:** none to separately obtain — installing the `silero-vad` package via
  `pip` is the complete provisioning step.
- **Authentication requirements:** none.
- **License:** **INFERRED / EXTERNAL** — not verified from anything in this repository; Silero
  VAD is publicly documented (outside this repo) as MIT-licensed.
- **Pretrained or fine-tuned:** pretrained, used zero-shot, no fine-tuning anywhere in this
  project targets this model.
- **Local weights exist:** yes, always — bundled with the pip install itself.
- **Runtime download dependency:** **no** — this is the one model in this entire stack that
  requires zero network access at any point, confirmed by direct inspection of the installed
  package's own files.
- **A genuine, project-specific quirk, not a model issue:** Silero's own `read_audio()` helper
  pulls in `torchaudio`'s `torchcodec` backend, which fails to load its native DLL on this Windows
  machine (reproduced directly this session, a large but non-fatal warning during `pytest`).
  `backend/services/audio_service.py: load_waveform()` avoids this entirely by using `soundfile`
  instead — the model itself is unaffected, only one particular *loading helper* around it.
- **Classification: IMPLEMENTED.**

## 3. SpeechBrain ECAPA-TDNN (teacher voice verification)

- **Model/algorithm name:** ECAPA-TDNN speaker embedding model.
- **Exact model identifier:** `speechbrain/spkrec-ecapa-voxceleb`.
- **Source/repository:** Hugging Face Hub, `https://huggingface.co/speechbrain/spkrec-ecapa-
  voxceleb`.
- **Version:** no pinned revision; package version `speechbrain==1.1.1` (confirmed via `pip
  freeze`).
- **Framework:** PyTorch, via the SpeechBrain toolkit's own `EncoderClassifier` wrapper.
- **Python package:** `speechbrain`.
- **Model download mechanism:** Automatic, via `EncoderClassifier.from_hparams(source=...,
  savedir=...)` — this call downloads through `huggingface_hub` into the standard HF cache
  **and then symlinks the result into the `savedir` path**, confirmed directly this pass: every
  file in the repo's own `models/speechbrain_spkrec-ecapa-voxceleb/` directory is a **symlink**,
  not a real copy, pointing at `~/.cache/huggingface/hub/models--speechbrain--spkrec-ecapa-
  voxceleb/snapshots/<hash>/...`.
- **Local model path:** **two locations, one real, one a symlink to it.** The real data:
  `~/.cache/huggingface/hub/models--speechbrain--spkrec-ecapa-voxceleb/` (**85MB**, confirmed via
  `du -sh` this pass). The symlink layer: `models/speechbrain_spkrec-ecapa-voxceleb/` inside the
  repo (gitignored, confirmed empty of any real bytes — every file there is a symlink).
- **Initialization code:** `backend/services/teacher_verification_service.py: load_
  verification_model()` → `EncoderClassifier.from_hparams(source=settings.
  speaker_verification_model, savedir=f"models/{settings.speaker_verification_model.replace('/',
  '_')}")`. Called from `celery_app.py: _load_models()`, wrapped in `try/except` (best-effort,
  same as Silero VAD).
- **Inference code:** `extract_embedding()` → `model.encode_batch(tensor)`, called from both
  teacher enrollment (`worker/tasks.py: enroll_teacher_task`) and per-segment verification
  (`audio_service.py: apply_teacher_verification()` → `teacher_verification_service.py:
  verify_segment()`).
- **Input format:** a mono float32 waveform tensor at 16kHz (enrollment sample, or a
  Whisper-segment-bounded slice).
- **Output format:** a fixed-length embedding vector, converted to a plain `list[float]` for JSON
  storage (ECAPA-TDNN's standard architecture output is 192-dimensional — not independently
  re-verified against this specific checkpoint's actual output shape this pass, stated as the
  architecture's well-known standard, not measured directly here).
- **Preprocessing:** the always-on FFmpeg standardization; teacher enrollment specifically was a
  documented past bug where this step was skipped (fixed in round 5, `CLAUDE.md` Part 2).
- **Postprocessing:** cosine similarity against every enrolled teacher's stored embedding —
  `cosine_similarity()`, best-match-wins.
- **Configuration:** `speaker_verification_model` (hardcoded string, not an env var —
  `backend/core/config.py` — despite most other model choices being env-var-configurable, this
  one is not), `TEACHER_VERIFICATION_THRESHOLD` (default `0.35`).
- **Thresholds:** `teacher_verification_threshold` — explicitly documented in the config file's
  own comment as "a typical VoxCeleb EER operating point... not yet calibrated against real
  classroom data."
- **Device selection:** none — `EncoderClassifier.from_hparams()` is called with no `run_opts`
  argument anywhere in this codebase, so it defaults to CPU.
- **VRAM implications:** none currently exercised — CPU-only in this project's entire history.
- **Expected model files:** the SpeechBrain checkpoint set — `classifier.ckpt`,
  `embedding_model.ckpt`, `hyperparams.yaml`, `label_encoder.ckpt` (a symlink to the source's
  `label_encoder.txt` — note the extension change, confirmed this pass), `mean_var_norm_emb.ckpt`.
- **Authentication requirements:** none — public, non-gated repository.
- **License:** **INFERRED / EXTERNAL** — not verified from this repository's own cache (no
  README/model-card cached locally, same as Whisper). SpeechBrain's toolkit is publicly documented
  (outside this repo) as Apache-2.0 licensed; this specific checkpoint's own terms were not
  independently confirmed here.
- **Pretrained or fine-tuned:** pretrained on VoxCeleb1+2, used entirely zero-shot — never
  fine-tuned on Hiligaynon/Filipino/English speakers or classroom audio anywhere in this project.
- **Local weights exist:** yes (via the cache+symlink mechanism above), but only after first use
  on a given machine.
- **Runtime download dependency:** **yes.**
- **Classification: IMPLEMENTED.**

## 4. pyannote.audio (speaker diarization)

- **Model/algorithm name:** `pyannote/speaker-diarization-community-1`.
- **Source/repository:** Hugging Face Hub — a **gated** repository, confirmed directly by this
  codebase's own error-handling text (`backend/services/diarization_service.py`): *"you haven't
  accepted the model's user conditions at https://huggingface.co/pyannote/speaker-diarization-
  community-1."*
- **Version:** no pinned revision. Package version `pyannote-audio==4.0.7` (plus
  `pyannote-core==6.0.1`, `pyannote-database==6.1.1`, `pyannote-metrics==4.1`,
  `pyannote-pipeline==4.0.0`, `pyannoteai-sdk==0.4.0` — all confirmed via `pip freeze`).
- **Framework:** PyTorch, via pyannote's own `Pipeline` abstraction.
- **Model download mechanism:** `Pipeline.from_pretrained(PIPELINE_NAME, token=hf_token)` — would
  download via `huggingface_hub` on first successful call, **given a valid token and accepted
  terms.**
- **Local model path:** **none exists on this machine.** Directly confirmed this pass: the real
  Hugging Face Hub cache directory (`~/.cache/huggingface/hub/`) contains exactly two model repos
  — `speechbrain--spkrec-ecapa-voxceleb` and `Systran--faster-whisper-small`. **There is no
  `pyannote` entry anywhere in the cache.** This is direct, physical evidence that this model has
  never been successfully downloaded in this project's entire development history.
- **Initialization code:** `backend/services/diarization_service.py: load_diarization_model()`,
  called from `celery_app.py: _load_models()` **only if `settings.hf_token` is truthy** —
  otherwise skipped entirely with a log message, no attempt made.
- **Inference code:** `diarize_audio()` → `pipeline(str(audio_path), **kwargs)`, called from
  `audio_service.py: run_pipeline()` only when `enable_diarization=True`.
- **Input format:** a file path (pyannote reads the file itself, unlike every other model in this
  stack, which take an in-memory waveform).
- **Output format:** a `DiarizeOutput` dataclass; `.speaker_diarization` is a pyannote
  `Annotation`, iterated via `.itertracks(yield_label=True)`.
- **Configuration:** `HF_TOKEN` env var (required — no default, `None` if unset), `enable_
  diarization` toggle (default `False`), optional `num_speakers` (auto-detected if not given).
- **Device selection:** none — no device argument passed anywhere.
- **VRAM implications:** unmeasured — diarization is described elsewhere in this project's own
  documentation as "the heaviest single stage in the pipeline" (`CLAUDE.md`), but no actual
  resource measurement exists for it, since it has never run.
- **Expected model files:** unknown exact size/file list — **never downloaded in this
  environment**, so nothing here can be measured directly; not guessed.
- **Authentication requirements:** a Hugging Face account, a personal access token
  (`HF_TOKEN`), **and** manually accepting this specific model's usage terms on huggingface.co
  before the token will work — this is a real, human, one-time action, not something automatable.
- **License:** **NOT DISCOVERABLE from this repository** — the model is gated specifically
  *because* it has non-standard usage terms; no license text is cached anywhere in this
  environment.
- **Pretrained or fine-tuned:** pretrained (community pipeline), never fine-tuned in this project.
- **Local weights exist:** **no — confirmed absent, not merely "unclear."**
- **Runtime download dependency:** yes, and additionally blocked on a manual, human,
  terms-acceptance step that has never been completed in this project's history.
- **Classification: PARTIALLY IMPLEMENTED.** The code is complete, reachable, toggleable, and one
  real bug in it was already found and fixed by code review (the `.itertracks` unpacking fix,
  round 9/10, `CLAUDE.md` Part 2) — but that fix has **never been confirmed against a real
  execution**, because the actual `pipeline(...)` call has never once fired successfully anywhere
  in this project's history (no cached model, no configured token, in any environment this
  project has run in). This is the one model in this audit where "the code looks done" and "the
  model has actually run" are provably different facts, not the same fact stated twice.

## 5. Hiligaynon-adapted Whisper (LoRA/PEFT fine-tune) — the project's own planned output model

- **Model/algorithm name:** a LoRA adapter over `openai/whisper-small`, intended to be merged and
  converted to a CTranslate2 directory for `faster-whisper` to load in place of `Systran/faster-
  whisper-small`.
- **Exact model identifier:** N/A — does not exist.
- **Source:** would be trained locally via `ai/finetuning/finetune_whisper.py` against a corpus
  that does not exist (`datasets/processed/` contains only a `.gitkeep`, confirmed this pass).
- **Framework/package:** `transformers==5.16.1`, `peft==0.20.0`, `accelerate==1.14.0`,
  `datasets==5.0.1` (all confirmed installed via `pip freeze` — the tooling is present even
  though it has never been exercised).
- **Model download mechanism:** the training script's own base-model load
  (`ai/finetuning/finetune_whisper.py: BASE_MODEL_NAME`) would pull `openai/whisper-small` (the
  original PyTorch weights, **not** the Systran CTranslate2 conversion §1 uses at inference time —
  a genuinely different artifact from the same underlying weights) via `transformers`, if this
  script were ever actually run.
- **Local model path:** N/A — never run, nothing exists to have a path.
- **Configuration:** would eventually be pointed at via `WHISPER_MODEL_SIZE` set to a local
  CTranslate2 directory path — this exact mechanism is already supported by `load_whisper_model()`
  (§1), confirmed by reading the code, even though nothing has ever populated it.
- **Whether pretrained or fine-tuned:** **neither, currently — it does not exist.**
- **Local weights exist:** **no.** Checked this pass: nothing in `datasets/processed/`, nothing
  in the gitignored `models/` directory beyond the SpeechBrain symlinks (§3), no `.safetensors`/
  `.bin`/CTranslate2-directory artifact anywhere in the repository or on this development machine.
- **Runtime download dependency:** N/A.
- **Classification: NOT PRESENT.** (Its *tooling* is IMPLEMENTED and unit-tested — see
  `docs/ML_PIPELINE.md` — but the model artifact itself, which is what this audit is about, does
  not exist.)

## 6. TextRank keyword extraction — algorithm, not a downloaded model

- **Model/algorithm name:** TextRank (Mihalcea & Tarau, 2004), implemented from scratch on top of
  `networkx`'s PageRank.
- **Exact model identifier:** N/A — no pretrained weights of any kind; this is a graph algorithm
  over tokenized text.
- **Framework/package:** `networkx==3.6.1` (confirmed via `pip freeze`).
- **Model download mechanism / local model path / authentication / VRAM / device selection:**
  **N/A for all of these** — there is no model file, no download, no device to select. This is
  deliberate and explicitly documented in the module's own docstring as a reason to avoid
  `nltk`/`sumy` specifically to avoid exactly this category of heavy-dependency/download overhead
  for what's "a small, well-understood graph algorithm."
- **Configuration:** a hand-curated trilingual stopword list (`backend/services/keyword_
  service.py: _STOPWORDS`), a co-occurrence window size (`_WINDOW_SIZE = 4`), `max_iter=200` for
  PageRank convergence with a weighted-degree-centrality fallback.
- **Classification: IMPLEMENTED.**

## 7. Rule-based minutes generation — algorithm, not a downloaded model

- **Model/algorithm name:** none — silence-gap topic segmentation, trilingual regex pattern
  matching for definitions/action-items, teacher-weighted sorting. Explicitly, by its own module
  docstring, "deliberately not an LLM/abstractive summarizer."
- **All model-specific fields (download mechanism, local path, device, VRAM, authentication,
  license) are N/A** — there is no model anywhere in this component; it is pure Python logic over
  already-transcribed text.
- **Classification: IMPLEMENTED** (as a heuristic — the module's own docstring is explicit that
  it "will miss/misfire on real classroom audio," a scope statement, not an implementation gap).

## 8. Models/frameworks referenced elsewhere but confirmed NOT PRESENT in this codebase

- **WhisperX** — grepped every file in this repository this pass and in the prior dependency-map
  pass: zero references anywhere, in code, `requirements*.txt`, or any doc. **NOT PRESENT.**
- **RNNoise / `pyrnnoise`** — was present historically, fully removed; zero references in any
  current `requirements*.txt` or import statement. **NOT PRESENT** (see `docs/
  ARCHITECTURE_DECISIONS.md` §9 for the removal history).
- **Any LLM (OpenAI/Anthropic/local Llama, etc.)** — no API client, no local inference library for
  any generative language model exists anywhere in `requirements*.txt` or the codebase. **NOT
  PRESENT.**

---

## Classification summary

| Model | Classification |
|---|---|
| Faster-Whisper (`Systran/faster-whisper-small`) | **IMPLEMENTED** |
| Silero VAD | **IMPLEMENTED** |
| SpeechBrain ECAPA-TDNN (`speechbrain/spkrec-ecapa-voxceleb`) | **IMPLEMENTED** |
| pyannote diarization (`pyannote/speaker-diarization-community-1`) | **PARTIALLY IMPLEMENTED** — code complete, never successfully executed in this project's history |
| Hiligaynon LoRA/PEFT-adapted Whisper | **NOT PRESENT** (tooling is implemented; the model artifact is not) |
| TextRank keyword extraction | **IMPLEMENTED** (algorithm, not a weighted model) |
| Rule-based minutes generation | **IMPLEMENTED** (algorithm, not a weighted model) |
| WhisperX | **NOT PRESENT** |
| RNNoise / `pyrnnoise` | **NOT PRESENT** (removed) |
| Any LLM | **NOT PRESENT** |

No model in this codebase was found to be **CONFIGURED BUT UNUSED**, **PLACEHOLDER**, or
**EXPERIMENTAL** under this audit's evidence — every model that has real loading code either runs
(§1–3) or has a real, named, specific blocker preventing it from ever having run (§4).

---

## The reproducibility question, answered directly

> **"If I delete the Python virtual environment and clone this repository onto another machine,
> exactly what model files must I obtain before the system can function?"**

**None, manually.** Every model this system actually uses at runtime provisions itself
automatically:

1. **Silero VAD** requires nothing beyond `pip install -r requirements.txt` — its model files are
   physically bundled inside the `silero-vad` package itself. Zero network access needed for this
   one specifically.
2. **Faster-Whisper (`Systran/faster-whisper-small`)** and **SpeechBrain (`speechbrain/spkrec-
   ecapa-voxceleb`)** both download automatically, the first time the worker process loads them,
   via each library's own Hugging Face Hub integration — **provided the new machine has outbound
   HTTPS access to huggingface.co.** No account or token is needed for either; both are public
   repositories. Expect roughly **464MB** (Whisper) + **85MB** (SpeechBrain) of first-run download,
   landing in `~/.cache/huggingface/hub/` (or the platform-equivalent path), entirely outside the
   cloned repository.
3. **Diarization (`pyannote/speaker-diarization-community-1`)** additionally requires: a real
   Hugging Face account, generating a personal access token, setting it as `HF_TOKEN`, **and**
   manually visiting the model's page on huggingface.co to accept its usage terms before the token
   will be honored. Skipping all of this is fully supported — the system runs correctly with
   diarization simply unavailable (logged, not an error) if `HF_TOKEN` is never set.
4. **The Hiligaynon fine-tuned model does not exist anywhere, on any machine, in any form.**
   There is nothing to obtain for it — running the system today, on any machine, means running the
   stock, unmodified `Systran/faster-whisper-small` weights regardless.

**What genuinely must be present before first use, that is not a "model file" in the ML sense:**
FFmpeg (`ffmpeg`/`ffprobe` executables on PATH — not a Python package, not downloaded by pip), and
enough free disk space for the ~550MB of automatic first-run model downloads above.

**What was verified by direct inspection, not assumed:** this machine's actual, real Hugging Face
cache was read directly this pass and confirmed to contain exactly two model repos (Whisper and
SpeechBrain) and zero pyannote entries — matching precisely what this project's own history says
about which models have ever actually run.
