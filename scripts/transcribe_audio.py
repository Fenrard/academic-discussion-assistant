import argparse
import sys
import time
from pathlib import Path

from faster_whisper import WhisperModel

MODEL_SIZE = "small"
DEVICE = "cpu"
COMPUTE_TYPE = "int8"


def load_model(model_size: str = MODEL_SIZE, device: str = DEVICE, compute_type: str = COMPUTE_TYPE) -> WhisperModel:
    try:
        return WhisperModel(model_size, device=device, compute_type=compute_type)
    except Exception as error:
        raise RuntimeError(f"Failed to load Whisper model '{model_size}': {error}")


def transcribe_audio(model: WhisperModel, audio_path: Path) -> dict:
    
    if not audio_path.exists():
        raise FileNotFoundError(f"No audio file found at: {audio_path}")

    start_time = time.perf_counter()

    try:
        segments, info = model.transcribe(str(audio_path), beam_size=5)
        segments = list(segments)  # faster-whisper returns a generator; consume it now
    except Exception as error:
        raise RuntimeError(f"Transcription failed on '{audio_path.name}': {error}")

    elapsed_seconds = time.perf_counter() - start_time

    full_text = " ".join(segment.text.strip() for segment in segments)

    segment_details = [
        {
            "start": round(segment.start, 2),
            "end": round(segment.end, 2),
            "text": segment.text.strip(),
            "avg_logprob": round(segment.avg_logprob, 4),
            "no_speech_prob": round(segment.no_speech_prob, 4),
        }
        for segment in segments
    ]

    return {
        "text": full_text,
        "language": info.language,
        "language_probability": round(info.language_probability, 4),
        "segments": segment_details,
        "elapsed_seconds": round(elapsed_seconds, 2),
    }


def print_results(result: dict) -> None:
  
    print(f"\nDetected language: {result['language']} (confidence: {result['language_probability']})")
    print(f"Transcription time: {result['elapsed_seconds']}s\n")

    print("Transcript:")
    print(result["text"])

    print("\nSegments:")
    for seg in result["segments"]:
        print(f"  [{seg['start']}s - {seg['end']}s] {seg['text']}  "
              f"(avg_logprob: {seg['avg_logprob']}, no_speech_prob: {seg['no_speech_prob']})")


def main() -> None:
   
    parser = argparse.ArgumentParser(description="Transcribe a preprocessed WAV file with Faster-Whisper.")
    parser.add_argument("audio_file", type=str, help="Path to a preprocessed WAV file.")
    args = parser.parse_args()

    audio_path = Path(args.audio_file).resolve()

    try:
        model = load_model()
        result = transcribe_audio(model, audio_path)
    except (FileNotFoundError, RuntimeError) as error:
        print(f"Error: {error}")
        sys.exit(1)

    print_results(result)


if __name__ == "__main__":
    main()