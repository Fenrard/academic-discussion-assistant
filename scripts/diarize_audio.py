"""
Speaker diarization module using pyannote.audio's community-1 pipeline.
Accepts a WAV file and returns structured speaker segments (Speaker A,
Speaker B, ...) with timestamps. Diarization only — no teacher
verification, no SpeechBrain matching. Written to be imported into
backend/services/ later, so nothing here is CLI-coupled beyond main().
"""

import argparse
import os
import sys
import time
from pathlib import Path

from pyannote.audio import Pipeline

PIPELINE_NAME = "pyannote/speaker-diarization-community-1"


def load_diarization_model(hf_token: str) -> Pipeline:
    """
    Loads the pretrained diarization pipeline. Requires a Hugging Face
    access token AND accepting the model's usage conditions on
    huggingface.co (it's a gated model) — see setup steps below.
    """
    if not hf_token:
        raise RuntimeError(
            "No Hugging Face token provided. Create one at "
            "https://huggingface.co/settings/tokens and pass it in "
            "(--hf-token or the HF_TOKEN environment variable)."
        )

    try:
        return Pipeline.from_pretrained(PIPELINE_NAME, token=hf_token)
    except Exception as error:
        raise RuntimeError(
            f"Failed to load diarization pipeline: {error}\n"
            f"Common causes: invalid token, or you haven't accepted the model's "
            f"user conditions at https://huggingface.co/{PIPELINE_NAME}"
        )


def diarize_audio(pipeline: Pipeline, audio_path: Path, num_speakers: int | None = None) -> list[tuple]:
    """
    Runs the pipeline and extracts raw (start, end, raw_label) tuples.
    Extracting into plain tuples here — rather than passing pyannote's
    own output object downstream — means only this function needs to
    know pyannote's specific output shape; everything after this is
    library-agnostic. num_speakers is optional: pass it only if you
    already know how many people are in the recording.
    """
    if not audio_path.exists():
        raise FileNotFoundError(f"No audio file found at: {audio_path}")

    try:
        kwargs = {"num_speakers": num_speakers} if num_speakers else {}
        output = pipeline(str(audio_path), **kwargs)
    except Exception as error:
        raise RuntimeError(f"Diarization failed on '{audio_path.name}': {error}")

    return [(turn.start, turn.end, speaker) for turn, speaker in output.speaker_diarization]


def format_speaker_segments(raw_segments: list[tuple]) -> list[dict]:
    """
    Maps pyannote's raw speaker labels to readable ones (Speaker A,
    Speaker B, ...) in order of first appearance, sorted by start time.
    Doesn't assume anything about the raw label's format — treats it as
    an opaque, hashable value, since that format isn't guaranteed stable
    across pyannote versions.
    """
    label_map: dict = {}
    formatted = []

    for start, end, raw_label in sorted(raw_segments, key=lambda s: s[0]):
        if raw_label not in label_map:
            label_map[raw_label] = _letter_for_index(len(label_map))

        formatted.append({
            "speaker": f"Speaker {label_map[raw_label]}",
            "start": round(start, 2),
            "end": round(end, 2),
            "duration": round(end - start, 2),
        })

    return formatted


def _letter_for_index(index: int) -> str:
    """0,1,2... -> A,B,C... (wraps to AA,AB... past 25 — unlikely, but cheap to handle)."""
    letters = ""
    index += 1
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def run_diarization(audio_path: Path, hf_token: str, num_speakers: int | None = None) -> dict:
    """Orchestrates load -> diarize -> format. Same shape as process_pipeline()."""
    start_time = time.perf_counter()

    pipeline = load_diarization_model(hf_token)
    raw_segments = diarize_audio(pipeline, audio_path, num_speakers=num_speakers)
    speaker_segments = format_speaker_segments(raw_segments)

    elapsed_seconds = round(time.perf_counter() - start_time, 2)
    unique_speakers = {seg["speaker"] for seg in speaker_segments}

    return {
        "speaker_segments": speaker_segments,
        "num_speakers_detected": len(unique_speakers),
        "processing_seconds": elapsed_seconds,
    }


def main() -> None:
    """CLI entry point for manual testing only."""
    parser = argparse.ArgumentParser(description="Run speaker diarization on a WAV file.")
    parser.add_argument("audio_file", type=str, help="Path to a preprocessed WAV file.")
    parser.add_argument("--hf-token", type=str, default=None, help="Hugging Face token (or set HF_TOKEN env var).")
    parser.add_argument("--num-speakers", type=int, default=None, help="Optional: exact number of speakers, if known.")
    args = parser.parse_args()

    audio_path = Path(args.audio_file).resolve()
    hf_token = args.hf_token or os.environ.get("HF_TOKEN")

    try:
        result = run_diarization(audio_path, hf_token, num_speakers=args.num_speakers)
    except (FileNotFoundError, RuntimeError) as error:
        print(f"Error: {error}")
        sys.exit(1)

    print(f"Speakers detected: {result['num_speakers_detected']}")
    print(f"Processing time: {result['processing_seconds']}s\n")

    for seg in result["speaker_segments"]:
        print(f"  [{seg['start']}s - {seg['end']}s] {seg['speaker']} ({seg['duration']}s)")


if __name__ == "__main__":
    main()