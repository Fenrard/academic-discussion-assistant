"""
Simulates chunked/streaming transcription by splitting an existing
preprocessed WAV file into fixed-duration chunks and running each one
independently through the existing pipeline (process_pipeline.py),
appending fragments into a growing transcript. No real streaming,
networking, or live microphone capture — this reproduces the
chunk-by-chunk *processing pattern* the real Android -> backend
pipeline will eventually use.
"""

import argparse
import os
import sys
import time
from pathlib import Path

import soundfile as sf
from faster_whisper import WhisperModel
from pyannote.audio import Pipeline

from process_pipeline import process_pipeline
from transcribe_audio import load_model
from diarize_audio import load_diarization_model

MIN_CHUNK_DURATION_SECONDS = 1.0
MAX_CHUNK_DURATION_SECONDS = 10.0
DEFAULT_CHUNK_DURATION_SECONDS = 3.0


def split_into_chunks(input_path: Path, chunk_duration_seconds: float = DEFAULT_CHUNK_DURATION_SECONDS) -> list[Path]:
    """
    Splits a preprocessed WAV file into sequential chunk WAVs (final
    chunk kept even if shorter). Bounded to 1-10s: below that, Whisper
    has too little context per chunk; above it, the latency benefit of
    chunking at all starts to disappear. Writes each chunk to its own
    file since process_pipeline() expects a path — the same handoff
    shape a real chunk-upload endpoint will use.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"No audio file found at: {input_path}")

    if not (MIN_CHUNK_DURATION_SECONDS <= chunk_duration_seconds <= MAX_CHUNK_DURATION_SECONDS):
        raise ValueError(
            f"chunk_duration_seconds must be between {MIN_CHUNK_DURATION_SECONDS} "
            f"and {MAX_CHUNK_DURATION_SECONDS}, got {chunk_duration_seconds}"
        )

    audio_data, sample_rate = sf.read(input_path, dtype="int16")
    samples_per_chunk = int(chunk_duration_seconds * sample_rate)

    chunk_dir = input_path.parent / f"{input_path.stem}_chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)

    chunk_paths = []
    total_samples = len(audio_data)

    for chunk_index, start_sample in enumerate(range(0, total_samples, samples_per_chunk)):
        end_sample = min(start_sample + samples_per_chunk, total_samples)
        chunk_audio = audio_data[start_sample:end_sample]

        chunk_path = chunk_dir / f"chunk_{chunk_index:04d}.wav"
        sf.write(chunk_path, chunk_audio, samplerate=sample_rate)
        chunk_paths.append(chunk_path)

    return chunk_paths


def process_chunk(
    chunk_path: Path,
    whisper_model: WhisperModel,
    chunk_index: int,
    enable_denoise: bool,
    enable_vad: bool,
    enable_diarization: bool,
    diarization_model: Pipeline | None,
) -> dict:
    """
    Runs one chunk through the pipeline as an isolated unit — no
    knowledge of neighboring chunks. Note: if enable_diarization is on,
    each chunk's speaker clustering restarts from scratch — "Speaker A"
    here has no guaranteed relation to "Speaker A" in the previous
    chunk. Fine for latency testing; not yet a correct cross-chunk
    speaker identity.
    """
    start_time = time.perf_counter()
    result = process_pipeline(
        chunk_path,
        whisper_model,
        enable_denoise=enable_denoise,
        enable_vad=enable_vad,
        enable_diarization=enable_diarization,
        diarization_model=diarization_model,
    )
    elapsed_seconds = round(time.perf_counter() - start_time, 2)

    return {
        "chunk_index": chunk_index,
        "chunk_path": str(chunk_path),
        "text": result["text"],
        "language": result["language"],
        "speaker_segments": result["speaker_segments"],
        "processing_seconds": elapsed_seconds,
    }


def simulate_streaming(
    input_path: Path,
    whisper_model: WhisperModel,
    chunk_duration_seconds: float = DEFAULT_CHUNK_DURATION_SECONDS,
    enable_denoise: bool = False,
    enable_vad: bool = True,
    enable_diarization: bool = False,
    diarization_model: Pipeline | None = None,
) -> dict:
    """
    Splits into chunks, processes each independently, appends fragments
    into one growing transcript in order. diarization_model, like
    whisper_model, is loaded once by the caller — not reloaded per
    chunk, which would be a real performance bug on longer recordings.
    """
    chunk_paths = split_into_chunks(input_path, chunk_duration_seconds)

    growing_transcript = ""
    chunk_results = []

    for index, chunk_path in enumerate(chunk_paths):
        chunk_result = process_chunk(
            chunk_path, whisper_model, index,
            enable_denoise, enable_vad, enable_diarization, diarization_model,
        )
        growing_transcript = (growing_transcript + " " + chunk_result["text"]).strip()

        print(
            f"[chunk {index + 1}/{len(chunk_paths)}] "
            f"{chunk_result['processing_seconds']}s processing -> \"{chunk_result['text']}\""
        )

        chunk_results.append(chunk_result)

    return {
        "transcript": growing_transcript,
        "chunks": chunk_results,
        "chunk_duration_seconds": chunk_duration_seconds,
    }


def main() -> None:
    """CLI entry point for manual testing only."""
    parser = argparse.ArgumentParser(description="Simulate chunked streaming transcription.")
    parser.add_argument("audio_file", type=str, help="Path to a preprocessed 16kHz mono WAV file.")
    parser.add_argument(
        "--chunk-seconds", type=float, default=DEFAULT_CHUNK_DURATION_SECONDS,
        help=f"Chunk duration in seconds, {MIN_CHUNK_DURATION_SECONDS}-{MAX_CHUNK_DURATION_SECONDS} "
             f"(default: {DEFAULT_CHUNK_DURATION_SECONDS})."
    )
    parser.add_argument("--denoise", action="store_true", help="Enable RNNoise denoising per chunk.")
    parser.add_argument("--no-vad", action="store_true", help="Skip Silero VAD per chunk.")
    parser.add_argument("--diarize", action="store_true", help="Enable per-chunk diarization (see caveat in process_chunk's docstring).")
    parser.add_argument("--hf-token", type=str, default=None, help="Hugging Face token, required only with --diarize (or set HF_TOKEN env var).")
    args = parser.parse_args()

    audio_path = Path(args.audio_file).resolve()

    try:
        whisper_model = load_model()

        diarization_model = None
        if args.diarize:
            hf_token = args.hf_token or os.environ.get("HF_TOKEN")
            diarization_model = load_diarization_model(hf_token)

        result = simulate_streaming(
            audio_path,
            whisper_model,
            chunk_duration_seconds=args.chunk_seconds,
            enable_denoise=args.denoise,
            enable_vad=not args.no_vad,
            enable_diarization=args.diarize,
            diarization_model=diarization_model,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"Error: {error}")
        sys.exit(1)

    print("\nFinal combined transcript:")
    print(result["transcript"])


if __name__ == "__main__":
    main()