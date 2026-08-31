"""
LoRA/PEFT fine-tuning of Faster-Whisper's base model (openai/whisper-small)
on the Hiligaynon classroom corpus — CLAUDE.md: "Fine-Tuning (IN SCOPE —
Non-Negotiable)". This is the training half; ai/finetuning/convert_to_faster_whisper.py
is the second half (merge the LoRA adapter into the base model, then
convert to CTranslate2 so backend/services/audio_service.py can load it
the same way it loads the stock model).

Not runnable to completion yet — datasets/ has no corpus in it (the
team's classroom recording + transcription pass is still underway per
CLAUDE.md's "Data Collection Tracking"). This script is the scaffold
that pass will run through once real data lands: `python
ai/finetuning/finetune_whisper.py datasets/processed/hiligaynon_corpus`.

Faster-Whisper itself (a CTranslate2 conversion) can't be trained
directly — LoRA fine-tuning happens against the original HuggingFace
`transformers` Whisper checkpoint, then gets converted. Standard recipe
(HF's Whisper fine-tuning guide + PEFT), nothing bespoke here.
"""

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

BASE_MODEL_NAME = "openai/whisper-small"
SAMPLE_RATE = 16000
TRAIN_EVAL_SPLIT_SEED = 42
EVAL_FRACTION = 0.1  # CLAUDE.md: "90/10 train/eval split"


@dataclass
class FinetuneConfig:
    dataset_path: Path
    output_dir: Path = Path("models") / "whisper-small-hiligaynon-lora"
    base_model_name: str = BASE_MODEL_NAME
    # No single forced language tag: Whisper doesn't have a Hiligaynon token at all (its
    # ~99 languages include "tl" for Filipino but not Hiligaynon), and forcing one would
    # fight the whole point of this corpus — natural three-way code-switching within one
    # utterance. build_lora_model() explicitly clears forced_decoder_ids for the same reason.
    # This is exactly CLAUDE.md's accepted "first-segment language lock" caveat, at training time.
    lora_r: int = 32
    lora_alpha: int = 64
    lora_dropout: float = 0.05
    lora_target_modules: list = field(default_factory=lambda: ["q_proj", "v_proj"])
    per_device_batch_size: int = 8
    gradient_accumulation_steps: int = 2
    learning_rate: float = 1e-3
    num_train_epochs: int = 3
    fp16: bool = True  # Colab GPU; flip off for CPU-only debugging runs
    eval_steps: int = 200
    save_steps: int = 200


def load_corpus(dataset_path: Path):
    """
    Loads a HuggingFace `datasets` dataset from disk (CLAUDE.md: "Format:
    HuggingFace dataset... stored in datasets/") and applies the locked
    90/10 split if it isn't already split. Expects an 'audio' column
    (path or {array, sampling_rate}) and a 'text' column (the
    ground-truth transcript, code-switched as naturally spoken).
    """
    from datasets import Audio, DatasetDict, load_from_disk

    if not dataset_path.exists():
        raise FileNotFoundError(
            f"No dataset found at: {dataset_path}. This is expected until the team's "
            f"classroom recording + transcription pass (CLAUDE.md's Data Collection "
            f"Tracking) has produced datasets/processed/<corpus_name>."
        )

    dataset = load_from_disk(str(dataset_path))

    if isinstance(dataset, DatasetDict) and "train" in dataset and "eval" in dataset:
        split = dataset
    else:
        split = dataset.train_test_split(test_size=EVAL_FRACTION, seed=TRAIN_EVAL_SPLIT_SEED)
        split = DatasetDict({"train": split["train"], "eval": split["test"]})

    return split.cast_column("audio", Audio(sampling_rate=SAMPLE_RATE))


def prepare_example(batch: dict, feature_extractor, tokenizer) -> dict:
    """Converts one {"audio", "text"} row into Whisper's expected {"input_features", "labels"}."""
    audio = batch["audio"]
    batch["input_features"] = feature_extractor(
        audio["array"], sampling_rate=audio["sampling_rate"]
    ).input_features[0]
    batch["labels"] = tokenizer(batch["text"]).input_ids
    return batch


@dataclass
class DataCollatorSpeechSeq2SeqWithPadding:
    """Pads input_features and labels independently; label padding is masked with -100 so it's ignored in the loss."""

    processor: object

    def __call__(self, features: list[dict]) -> dict:
        import torch

        input_features = [{"input_features": f["input_features"]} for f in features]
        batch = self.processor.feature_extractor.pad(input_features, return_tensors="pt")

        label_features = [{"input_ids": f["labels"]} for f in features]
        labels_batch = self.processor.tokenizer.pad(label_features, return_tensors="pt")
        labels = labels_batch["input_ids"].masked_fill(labels_batch.attention_mask.ne(1), -100)

        if (labels[:, 0] == self.processor.tokenizer.bos_token_id).all().cpu().item():
            labels = labels[:, 1:]

        batch["labels"] = labels
        return batch


def build_lora_model(config: FinetuneConfig):
    """Loads the base Whisper checkpoint and wraps its attention projections with a LoRA adapter."""
    from peft import LoraConfig, get_peft_model
    from transformers import WhisperForConditionalGeneration

    base_model = WhisperForConditionalGeneration.from_pretrained(config.base_model_name)
    base_model.config.forced_decoder_ids = None
    base_model.config.suppress_tokens = []

    lora_config = LoraConfig(
        r=config.lora_r,
        lora_alpha=config.lora_alpha,
        target_modules=config.lora_target_modules,
        lora_dropout=config.lora_dropout,
        bias="none",
    )
    return get_peft_model(base_model, lora_config)


def build_compute_metrics(tokenizer):
    """WER via evaluation/wer.py's own edit-distance implementation — reused rather than pulling in jiwer twice."""
    from evaluation.wer import word_error_rate

    def compute_metrics(eval_pred) -> dict:
        predictions, label_ids = eval_pred.predictions, eval_pred.label_ids
        label_ids[label_ids == -100] = tokenizer.pad_token_id

        predicted_texts = tokenizer.batch_decode(predictions, skip_special_tokens=True)
        reference_texts = tokenizer.batch_decode(label_ids, skip_special_tokens=True)

        rates = [word_error_rate(ref, hyp) for ref, hyp in zip(reference_texts, predicted_texts) if ref.strip()]
        return {"wer": sum(rates) / len(rates) if rates else 0.0}

    return compute_metrics


def train(config: FinetuneConfig) -> Path:
    """Runs the LoRA fine-tune end to end; returns the directory the adapter was saved to."""
    from transformers import (
        Seq2SeqTrainer,
        Seq2SeqTrainingArguments,
        WhisperFeatureExtractor,
        WhisperProcessor,
        WhisperTokenizer,
    )

    dataset = load_corpus(config.dataset_path)

    feature_extractor = WhisperFeatureExtractor.from_pretrained(config.base_model_name)
    tokenizer = WhisperTokenizer.from_pretrained(config.base_model_name, task="transcribe")
    processor = WhisperProcessor.from_pretrained(config.base_model_name, task="transcribe")

    dataset = dataset.map(
        lambda batch: prepare_example(batch, feature_extractor, tokenizer),
        remove_columns=dataset["train"].column_names,
        num_proc=1,
    )

    model = build_lora_model(config)
    data_collator = DataCollatorSpeechSeq2SeqWithPadding(processor=processor)
    compute_metrics = build_compute_metrics(tokenizer)

    config.output_dir.mkdir(parents=True, exist_ok=True)
    training_args = Seq2SeqTrainingArguments(
        output_dir=str(config.output_dir),
        per_device_train_batch_size=config.per_device_batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        learning_rate=config.learning_rate,
        num_train_epochs=config.num_train_epochs,
        fp16=config.fp16,
        eval_strategy="steps",
        eval_steps=config.eval_steps,
        save_steps=config.save_steps,
        predict_with_generate=True,
        generation_max_length=225,
        logging_steps=25,
        report_to=[],
    )

    trainer = Seq2SeqTrainer(
        args=training_args,
        model=model,
        train_dataset=dataset["train"],
        eval_dataset=dataset["eval"],
        data_collator=data_collator,
        compute_metrics=compute_metrics,
    )

    trainer.train()
    trainer.save_model(str(config.output_dir))
    processor.save_pretrained(str(config.output_dir))

    return config.output_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="LoRA fine-tune Whisper-small on the Hiligaynon classroom corpus.")
    parser.add_argument("dataset_path", type=str, help="Path to a HuggingFace dataset saved via Dataset.save_to_disk().")
    parser.add_argument("--output-dir", type=str, default=str(FinetuneConfig.output_dir))
    parser.add_argument("--epochs", type=int, default=FinetuneConfig.num_train_epochs)
    parser.add_argument("--batch-size", type=int, default=FinetuneConfig.per_device_batch_size)
    parser.add_argument("--cpu", action="store_true", help="Disable fp16 for a CPU-only debugging run.")
    args = parser.parse_args()

    config = FinetuneConfig(
        dataset_path=Path(args.dataset_path),
        output_dir=Path(args.output_dir),
        num_train_epochs=args.epochs,
        per_device_batch_size=args.batch_size,
        fp16=not args.cpu,
    )

    try:
        output_dir = train(config)
    except (FileNotFoundError, RuntimeError) as error:
        print(f"Error: {error}")
        sys.exit(1)

    print(f"LoRA adapter saved to: {output_dir}")
    print("Next: ai/finetuning/convert_to_faster_whisper.py to merge + convert for backend use.")


if __name__ == "__main__":
    main()
