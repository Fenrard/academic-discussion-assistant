# Fine-tuning (LoRA/PEFT on Faster-Whisper small)

Two-step pipeline, per CLAUDE.md's locked tech stack (`LoRA/PEFT on
Faster-Whisper small`, trained on `Google Colab (free GPU)`). **Not
runnable yet** — it needs a real dataset in `datasets/processed/` first,
which is the team's in-progress classroom recording + transcription
pass (CLAUDE.md's "Data Collection Tracking"). This is the scaffold
that pass runs through once that data exists.

## 1. Dataset format

A HuggingFace `datasets.Dataset` (or `DatasetDict` with `train`/`eval`
already split) saved via `Dataset.save_to_disk("datasets/processed/<corpus_name>")`,
with columns:

- `audio` — a path to a 16kHz mono WAV, or `{"array": ..., "sampling_rate": ...}`
- `text` — the ground-truth transcript, code-switched exactly as spoken (don't normalize away the Hiligaynon/Filipino/English mixing — that's the point of this corpus)

If the dataset isn't pre-split, `finetune_whisper.py` applies CLAUDE.md's
locked 90/10 train/eval split itself (seeded, so it's reproducible).

## 2. Train the LoRA adapter

On Colab (GPU runtime):

```bash
pip install -r requirements.txt
python ai/finetuning/finetune_whisper.py datasets/processed/hiligaynon_corpus \
  --output-dir models/whisper-small-hiligaynon-lora \
  --epochs 3 --batch-size 8
```

Trains against the original `openai/whisper-small` HF checkpoint (not
the CTranslate2 conversion faster-whisper uses at inference — LoRA
needs the real `transformers` model). No language is forced during
training or decoding — see the comment in `finetune_whisper.py`'s
`FinetuneConfig` for why that matters for a code-switched corpus.
WER is tracked during eval using `evaluation/wer.py`'s own edit-distance
implementation, not a new dependency.

## 3. Merge + convert for backend use

```bash
python ai/finetuning/convert_to_faster_whisper.py models/whisper-small-hiligaynon-lora
```

Merges the adapter into the base model, then runs
`ct2-transformers-converter` (ships with the already-installed
`ctranslate2` package) to produce a CTranslate2 directory —
`models/whisper-small-hiligaynon-lora_ct2` by default.

## 4. Point the backend at it

`backend/services/audio_service.load_whisper_model()` passes
`backend/core/config.py`'s `settings.whisper_model_size` straight to
`WhisperModel(...)`, which accepts a local CTranslate2 directory path
in place of a model name. Set:

```
setx WHISPER_MODEL_SIZE "C:\...\models\whisper-small-hiligaynon-lora_ct2"
```

and restart the backend — no code change needed.
