# datasets/

Fine-tuning corpus staging area (CLAUDE.md: "real classroom recordings
by Nathan; naturally occurring Ilonggo code-switched speech... stored
in `datasets/`"). Empty until the team's recording + transcription pass
produces something to put here — see `ai/finetuning/README.md` for the
format `processed/` needs to be in.

| Folder | Contents |
|---|---|
| `raw/` | Unedited classroom recordings as collected (any format/sample rate) |
| `clean/` | After `scripts/preprocess_audio.py`-style standardization (16kHz mono WAV) |
| `processed/` | Final `datasets.Dataset` corpora, saved via `Dataset.save_to_disk()` — what `ai/finetuning/finetune_whisper.py` reads |
| `metadata/` | Transcripts, speaker labels, consent/ethics-clearance records per recording |

All audio in here is gitignored (`recordings/`, `*.wav` in `.gitignore`)
— this structure is tracked, the data itself isn't.
