"""
Second half of the fine-tuning pipeline: merges the LoRA adapter
finetune_whisper.py produced into the base Whisper weights, then
converts the merged model to CTranslate2 format so it loads through
faster-whisper exactly like the stock model does
(backend.services.audio_service.load_whisper_model() just needs
WHISPER_MODEL_SIZE — or rather its path — pointed at the converted
directory; see this file's docstring bottom for the one-line change).

CTranslate2 can't consume a PEFT adapter directly — it converts a plain
HuggingFace `transformers` checkpoint, so the merge step has to happen
first. Uses the `ct2-transformers-converter` CLI that ships with the
`ctranslate2` package (already a faster-whisper dependency, nothing new
to install), the same subprocess.run pattern the rest of this codebase
already uses for ffmpeg.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.finetuning.finetune_whisper import BASE_MODEL_NAME  # noqa: E402


def merge_lora_adapter(adapter_dir: Path, merged_output_dir: Path, base_model_name: str = BASE_MODEL_NAME) -> Path:
    """Loads the base model + LoRA adapter, folds the adapter weights in, and saves a plain HF checkpoint."""
    from peft import PeftModel
    from transformers import WhisperForConditionalGeneration, WhisperProcessor

    if not adapter_dir.exists():
        raise FileNotFoundError(f"No LoRA adapter found at: {adapter_dir} — run finetune_whisper.py first.")

    base_model = WhisperForConditionalGeneration.from_pretrained(base_model_name)
    adapted_model = PeftModel.from_pretrained(base_model, str(adapter_dir))
    merged_model = adapted_model.merge_and_unload()

    merged_output_dir.mkdir(parents=True, exist_ok=True)
    merged_model.save_pretrained(str(merged_output_dir))

    processor = WhisperProcessor.from_pretrained(str(adapter_dir))
    processor.save_pretrained(str(merged_output_dir))

    return merged_output_dir


def convert_to_ctranslate2(merged_model_dir: Path, output_dir: Path, quantization: str = "int8") -> Path:
    """Shells out to ct2-transformers-converter — same quantization faster-whisper's stock 'small' model uses."""
    if shutil.which("ct2-transformers-converter") is None:
        raise EnvironmentError(
            "'ct2-transformers-converter' not found on PATH. It ships with the 'ctranslate2' "
            "pip package (already installed) — if it's still missing, reinstall with "
            "'pip install --force-reinstall ctranslate2'."
        )

    command = [
        "ct2-transformers-converter",
        "--model", str(merged_model_dir),
        "--output_dir", str(output_dir),
        "--quantization", quantization,
        "--copy_files", "tokenizer.json", "preprocessor_config.json",
        "--force",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ct2-transformers-converter failed: {result.stderr.strip()}")

    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge a LoRA adapter into Whisper and convert it for faster-whisper.")
    parser.add_argument("adapter_dir", type=str, help="Directory finetune_whisper.py saved the LoRA adapter to.")
    parser.add_argument("--merged-dir", type=str, default=None, help="Where to save the merged HF checkpoint (default: <adapter_dir>_merged).")
    parser.add_argument("--output-dir", type=str, default=None, help="Where to save the final CTranslate2 model (default: <adapter_dir>_ct2).")
    parser.add_argument("--quantization", type=str, default="int8", help="Matches WHISPER_COMPUTE_TYPE in backend/core/config.py (default: int8).")
    args = parser.parse_args()

    adapter_dir = Path(args.adapter_dir).resolve()
    merged_dir = Path(args.merged_dir).resolve() if args.merged_dir else adapter_dir.with_name(adapter_dir.name + "_merged")
    output_dir = Path(args.output_dir).resolve() if args.output_dir else adapter_dir.with_name(adapter_dir.name + "_ct2")

    try:
        merge_lora_adapter(adapter_dir, merged_dir)
        convert_to_ctranslate2(merged_dir, output_dir, quantization=args.quantization)
    except (FileNotFoundError, EnvironmentError, RuntimeError) as error:
        print(f"Error: {error}")
        sys.exit(1)

    print(f"Converted model ready at: {output_dir}")
    print(
        "To use it: point backend/core/config.py's WHISPER_MODEL_SIZE env var "
        f"(WHISPER_MODEL_SIZE) at this path — WhisperModel(str(output_dir), ...) "
        "accepts a local CTranslate2 directory in place of a model name."
    )


if __name__ == "__main__":
    main()
