"""
Speech-processing pipeline prototype: FFmpeg standardization (always on)
-> (optional) FFmpeg afftdn denoising -> (optional) Silero VAD ->
Faster-Whisper transcription -> (optional) pyannote diarization +
speaker-label merge. Every stage after standardization can be switched
off independently, so a classroom situation can trade transcript
completeness for latency rather than always paying for the full stack.

Kept in step with backend/services/audio_service.py, which this file's
logic was promoted into: standardization is unconditional here now too
(CLAUDE.md rule 1 — "FFmpeg preprocessing is ALWAYS ON"), and denoising
is FFmpeg's afftdn filter, not the old pyrnnoise/RNNoise round-trip that
broke against current audiolab/PyAV (see docs/paper-vs-implementation.md
§3.3).
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import torch
import soundfile as sf
import numpy as np
from faster_whisper import WhisperModel
from pyannote.audio import Pipeline
from silero_vad import load_silero_vad, get_speech_timestamps

from transcribe_audio import load_model
from diarize_audio import (
    load_diarization_model,
    diarize_audio as run_diarization_stage,
    format_speaker_segments,
)

SAMPLE_RATE = 16000
# Same afftdn defaults as backend/services/audio_service.py's DENOISE_FILTER —
# an unvalidated starting point, tune against real noisy classroom audio.
DENOISE_FILTER = "afftdn=nr=12:nf=-25:tn=1"


def standardize_audio(input_path: Path, output_path: Path) -> Path:
    """
    FFmpeg: any input -> 16kHz mono PCM WAV + loudnorm. Always runs, no
    toggle (CLAUDE.md rule 1). Mirrors audio_service.ingest_audio(). Even
    an already-preprocessed WAV benefits: Whisper's repetition-loop
    hallucination on a short truncated clip is sensitive to the exact
    waveform, and normalizing here is what keeps it stable.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"No audio file found at: {input_path}")

    command = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-ar", str(SAMPLE_RATE),
        "-ac", "1",
        "-c:a", "pcm_s16le",
        "-af", "loudnorm",
        str(output_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg standardization failed on '{input_path.name}': {result.stderr.strip()}")

    return output_path


def clean_audio(input_path: Path, enable_denoise: bool = False) -> Path:
    """
    Optionally runs FFmpeg's afftdn (FFT denoise) in place at 16kHz. When
    enable_denoise is False, returns the input path unchanged and does no
    work at all — skipping this stage costs nothing, the point of a toggle.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"No audio file found at: {input_path}")

    if not enable_denoise:
        return input_path

    cleaned_path = input_path.with_name(input_path.stem + "_cleaned.wav")
    command = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-af", DENOISE_FILTER,
        "-ar", str(SAMPLE_RATE),
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(cleaned_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        cleaned_path.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg denoise (afftdn) failed on '{input_path.name}': {result.stderr.strip()}")

    return cleaned_path


def detect_speech(audio_path: Path, enable_vad: bool = True) -> tuple[np.ndarray, list[dict]]:
    """
    Loads the (possibly denoised) 16kHz audio and, if enabled, runs
    Silero VAD. When enable_vad is False, skips the model entirely (not
    just its result) and returns one segment spanning the whole file —
    transcribe_audio() runs unchanged either way, since it only ever
    iterates over whatever segments it's given.
    """
    if not audio_path.exists():
        raise FileNotFoundError(f"No audio file found at: {audio_path}")

    if not enable_vad:
        waveform = _load_waveform(audio_path).numpy()
        whole_file_segment = [{
            "start_sample": 0,
            "end_sample": len(waveform),
            "start_seconds": 0.0,
            "end_seconds": round(len(waveform) / SAMPLE_RATE, 2),
        }]
        return waveform, whole_file_segment

    vad_model = load_silero_vad()
    waveform = _load_waveform(audio_path)

    raw_timestamps = get_speech_timestamps(waveform, vad_model, sampling_rate=SAMPLE_RATE)

    speech_segments = [
        {
            "start_sample": ts["start"],
            "end_sample": ts["end"],
            "start_seconds": round(ts["start"] / SAMPLE_RATE, 2),
            "end_seconds": round(ts["end"] / SAMPLE_RATE, 2),
        }
        for ts in raw_timestamps
    ]

    return waveform.numpy(), speech_segments


def transcribe_audio(model: WhisperModel, waveform: np.ndarray, speech_segments: list[dict]) -> dict:
    """
    Runs Faster-Whisper on each given segment — whether that's several
    VAD-detected segments or one segment spanning the whole file. Has no
    idea whether VAD ran, which is exactly the point. Distinct from
    transcribe_audio() in transcribe_audio.py — same name, different
    signature.
    """
    all_text_parts = []
    all_whisper_segments = []
    detected_language = None
    language_probability = None

    start_time = time.perf_counter()

    for vad_segment in speech_segments:
        clip = waveform[vad_segment["start_sample"]:vad_segment["end_sample"]]
        if clip.size == 0:
            continue

        try:
            segments, info = model.transcribe(clip, beam_size=5)
            segments = list(segments)
        except Exception as error:
            raise RuntimeError(f"Transcription failed on segment {vad_segment}: {error}")

        if detected_language is None:
            detected_language = info.language
            language_probability = round(info.language_probability, 4)

        offset = vad_segment["start_seconds"]
        for seg in segments:
            all_text_parts.append(seg.text.strip())
            all_whisper_segments.append({
                "start": round(offset + seg.start, 2),
                "end": round(offset + seg.end, 2),
                "text": seg.text.strip(),
                "avg_logprob": round(seg.avg_logprob, 4),
                "no_speech_prob": round(seg.no_speech_prob, 4),
            })

    elapsed_seconds = round(time.perf_counter() - start_time, 2)

    return {
        "text": " ".join(all_text_parts),
        "language": detected_language,
        "language_probability": language_probability,
        "transcription_seconds": elapsed_seconds,
        "speech_segments": speech_segments,
        "whisper_segments": all_whisper_segments,
    }

def _load_waveform(audio_path: Path) -> torch.Tensor:
    """
    Loads a WAV as a float32 torch tensor, replacing silero_vad's
    read_audio() — that pulls in torchaudio's torchcodec backend, which
    needs FFmpeg's shared DLLs specifically, not the ffmpeg/ffprobe
    executables already installed.
    """
    audio_data, sample_rate = sf.read(audio_path, dtype="float32")
    if sample_rate != SAMPLE_RATE:
        raise ValueError(f"Expected {SAMPLE_RATE}Hz audio, got {sample_rate}Hz: {audio_path}")
    return torch.from_numpy(audio_data)

def merge_transcript_with_speakers(whisper_segments: list[dict], speaker_segments: list[dict]) -> list[dict]:
    """
    Attaches a speaker label to each Whisper segment by finding which
    diarization segment overlaps it the most in time — the merge step
    left unbuilt when diarize_audio.py shipped standalone, since the two
    outputs only share a timeline, not a data structure. A segment with
    no overlapping speaker (a diarization gap) falls back to "Unknown"
    rather than crashing.
    """
    labeled_segments = []

    for whisper_seg in whisper_segments:
        best_speaker = "Unknown"
        best_overlap = 0.0

        for speaker_seg in speaker_segments:
            overlap_start = max(whisper_seg["start"], speaker_seg["start"])
            overlap_end = min(whisper_seg["end"], speaker_seg["end"])
            overlap_duration = max(0.0, overlap_end - overlap_start)

            if overlap_duration > best_overlap:
                best_overlap = overlap_duration
                best_speaker = speaker_seg["speaker"]

        labeled_segments.append({**whisper_seg, "speaker": best_speaker})

    return labeled_segments


def process_pipeline(
    input_path: Path,
    whisper_model: WhisperModel,
    enable_denoise: bool = False,
    enable_vad: bool = True,
    enable_diarization: bool = False,
    diarization_model: Pipeline | None = None,
    num_speakers: int | None = None,
) -> dict:
    """
    Orchestrates the pipeline: standardize_audio (always) -> clean_audio
    (optional) -> detect_speech -> transcribe_audio -> (optional)
    diarization + speaker merge.

    diarization_model, like whisper_model, must already be loaded and
    passed in — loading pyannote's pipeline is expensive and should
    happen once at startup, not per call, same reasoning as load_model().

    Teacher verification isn't wired in yet. Once built, it slots in
    right after diarization, gated by its own enable_teacher_verification
    flag, comparing each speaker cluster against the enrolled embedding.
    """
    if enable_diarization and diarization_model is None:
        raise ValueError("enable_diarization=True requires a loaded diarization_model.")
    if not input_path.exists():
        raise FileNotFoundError(f"No audio file found at: {input_path}")

    standardized_path = None
    cleaned_path = None
    try:
        standardized_path = standardize_audio(input_path, input_path.with_name(input_path.stem + "_std.wav"))
        cleaned_path = clean_audio(standardized_path, enable_denoise)
        waveform, speech_segments = detect_speech(cleaned_path, enable_vad)
        result = transcribe_audio(whisper_model, waveform, speech_segments)

        if enable_diarization:
            raw_speaker_segments = run_diarization_stage(diarization_model, cleaned_path, num_speakers=num_speakers)
            speaker_segments = format_speaker_segments(raw_speaker_segments)
            result["whisper_segments"] = merge_transcript_with_speakers(result["whisper_segments"], speaker_segments)
            result["speaker_segments"] = speaker_segments
        else:
            result["speaker_segments"] = []

        return result
    finally:
        # Clean up the FFmpeg intermediates regardless of outcome — the input
        # file the caller passed in is left untouched.
        for temp_path in (cleaned_path, standardized_path):
            if temp_path is not None and temp_path != input_path:
                temp_path.unlink(missing_ok=True)


def main() -> None:
    """CLI entry point for manual testing only."""
    parser = argparse.ArgumentParser(description="Run the configurable denoise/VAD/diarization -> Whisper pipeline.")
    parser.add_argument("audio_file", type=str, help="Path to an audio file (any format FFmpeg can read; standardized before use).")
    parser.add_argument("--denoise", action="store_true", help="Enable FFmpeg afftdn denoising before VAD.")
    parser.add_argument("--no-vad", action="store_true", help="Skip Silero VAD; transcribe the whole file as one segment.")
    parser.add_argument("--diarize", action="store_true", help="Enable pyannote diarization and merge speaker labels into the transcript.")
    parser.add_argument("--hf-token", type=str, default=None, help="Hugging Face token, required only with --diarize (or set HF_TOKEN env var).")
    parser.add_argument("--num-speakers", type=int, default=None, help="Optional: exact number of speakers, if known.")
    args = parser.parse_args()

    audio_path = Path(args.audio_file).resolve()

    try:
        whisper_model = load_model()

        diarization_model = None
        if args.diarize:
            hf_token = args.hf_token or os.environ.get("HF_TOKEN")
            diarization_model = load_diarization_model(hf_token)

        result = process_pipeline(
            audio_path,
            whisper_model,
            enable_denoise=args.denoise,
            enable_vad=not args.no_vad,
            enable_diarization=args.diarize,
            diarization_model=diarization_model,
            num_speakers=args.num_speakers,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"Error: {error}")
        sys.exit(1)

    print(f"\nDetected language: {result['language']} (confidence: {result['language_probability']})")
    print(f"Transcription time: {result['transcription_seconds']}s")
    print(f"Speech segments detected: {len(result['speech_segments'])}")

    print("\nTranscript:")
    print(result["text"])

    print("\nWhisper segments:")
    for seg in result["whisper_segments"]:
        speaker_tag = f" [{seg['speaker']}]" if "speaker" in seg else ""
        print(f"  [{seg['start']}s - {seg['end']}s]{speaker_tag} {seg['text']}  "
              f"(avg_logprob: {seg['avg_logprob']}, no_speech_prob: {seg['no_speech_prob']})")


if __name__ == "__main__":
    main()