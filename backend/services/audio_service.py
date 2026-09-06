"""
The pipeline orchestrator — the backend-service promotion of
scripts/process_pipeline.py (CLAUDE.md build-priority item #1), plus
the pieces that script didn't have:

  - FFmpeg preprocessing is now actually always-on end-to-end. CLAUDE.md
    locks this as a rule ("FFmpeg preprocessing is ALWAYS ON — never
    toggleable"), but process_pipeline.py never called it — preprocessing
    only happened as a separate manual CLI step before that script ran.
    ingest_audio() below closes that gap: every chunk/file, denoise-toggle
    or not, gets FFmpeg-normalized first.
  - Glossary refinement, right after transcription (per-chunk).
  - Teacher verification, right after diarization.
  - Per-stage latency timing on every call, for evaluation/latency.py.

Every stage after ingest still has its own independent toggle, per
CLAUDE.md's locked pipeline order. Models are loaded once by the FastAPI
lifespan (backend/main.py) and passed in here — never reloaded per call.
"""

import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from faster_whisper import WhisperModel
from pyannote.audio import Pipeline
from silero_vad import get_speech_timestamps, load_silero_vad

from backend.core.config import settings
from backend.services import diarization_service, teacher_verification_service
from backend.services.glossary_service import Glossary

SAMPLE_RATE = settings.sample_rate
RNNOISE_SAMPLE_RATE = settings.rnnoise_sample_rate
SUPPORTED_EXTENSIONS = (".wav", ".mp3", ".m4a", ".ogg", ".webm", ".flac", ".aac")


def load_whisper_model() -> WhisperModel:
    """Backend-service copy of scripts/transcribe_audio.py's load_model() — loaded once at FastAPI startup."""
    try:
        return WhisperModel(
            settings.whisper_model_size,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
    except Exception as error:
        raise RuntimeError(f"Failed to load Whisper model '{settings.whisper_model_size}': {error}")


@dataclass
class LoadedModels:
    """Bundled once-loaded models, held on app.state and passed into every pipeline call."""

    whisper_model: WhisperModel
    diarization_model: Pipeline | None = None
    teacher_verification_model: object | None = None
    silero_vad_model: object | None = None
    glossary: Glossary = field(default_factory=lambda: Glossary({}))


class StageTimer:
    """Small helper so every stage's elapsed time lands in one dict without repeating perf_counter boilerplate."""

    def __init__(self):
        self.latencies: dict[str, float] = {}

    def track(self, stage_name: str):
        return _StageTimerContext(self, stage_name)


class _StageTimerContext:
    def __init__(self, timer: StageTimer, stage_name: str):
        self._timer = timer
        self._stage_name = stage_name

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_exc_info):
        self._timer.latencies[self._stage_name] = round(time.perf_counter() - self._start, 4)


def ingest_audio(input_path: Path, output_path: Path) -> Path:
    """
    FFmpeg standardization: any supported input -> 16kHz mono PCM WAV with
    loudnorm applied. Always runs, unconditionally — this is the one
    stage in the pipeline with no toggle. Same command as
    scripts/preprocess_audio.py's preprocess_audio().
    """
    if not input_path.exists():
        raise FileNotFoundError(f"No audio file found at: {input_path}")
    if input_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{input_path.suffix}'. Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
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
        raise RuntimeError(f"ffmpeg preprocessing failed on '{input_path.name}': {result.stderr.strip()}")

    return output_path


def clean_audio(input_path: Path, enable_denoise: bool) -> Path:
    """RNNoise denoising via pyrnnoise's 48kHz round-trip. Skipped entirely (not just its result) when disabled."""
    if not enable_denoise:
        return input_path

    try:
        from pyrnnoise import RNNoise
    except ImportError:
        raise RuntimeError(
            "pyrnnoise is not installed. Install with 'pip install pyrnnoise', "
            "or call with enable_denoise=False to skip this stage."
        )

    upsampled_path = input_path.with_name(input_path.stem + "_48k.wav")
    denoised_48k_path = input_path.with_name(input_path.stem + "_48k_denoised.wav")
    cleaned_path = input_path.with_name(input_path.stem + "_cleaned.wav")

    # In a `finally`, not just after the last step succeeds: if the second
    # resample (or RNNoise itself) raises, both intermediate 48kHz files
    # would otherwise leak to disk permanently — the exact privacy property
    # CLAUDE.md documents ("temp files cleaned up in finally blocks") this
    # function itself needs to uphold, not just its callers.
    try:
        _run_ffmpeg_resample(input_path, upsampled_path, RNNOISE_SAMPLE_RATE)

        denoiser = RNNoise(sample_rate=RNNOISE_SAMPLE_RATE)
        for _ in denoiser.denoise_wav(str(upsampled_path), str(denoised_48k_path)):
            pass

        _run_ffmpeg_resample(denoised_48k_path, cleaned_path, SAMPLE_RATE)
    finally:
        upsampled_path.unlink(missing_ok=True)
        denoised_48k_path.unlink(missing_ok=True)

    return cleaned_path


def _run_ffmpeg_resample(input_path: Path, output_path: Path, target_sample_rate: int) -> None:
    command = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-ar", str(target_sample_rate),
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(output_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg resample to {target_sample_rate}Hz failed: {result.stderr.strip()}")


def detect_speech(audio_path: Path, enable_vad: bool, silero_vad_model=None) -> tuple[np.ndarray, list[dict]]:
    """When enable_vad is False, skips the model and returns one whole-file segment."""
    if not audio_path.exists():
        raise FileNotFoundError(f"No audio file found at: {audio_path}")

    if not enable_vad:
        waveform = load_waveform(audio_path).numpy()
        return waveform, [{
            "start_sample": 0,
            "end_sample": len(waveform),
            "start_seconds": 0.0,
            "end_seconds": round(len(waveform) / SAMPLE_RATE, 2),
        }]

    vad_model = silero_vad_model or load_silero_vad()
    waveform = load_waveform(audio_path)
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


def load_waveform(audio_path: Path) -> torch.Tensor:
    """soundfile, not silero_vad's read_audio() — see CLAUDE.md's note on the torchcodec/FFmpeg DLL conflict on Windows."""
    audio_data, sample_rate = sf.read(audio_path, dtype="float32")
    if sample_rate != SAMPLE_RATE:
        raise ValueError(f"Expected {SAMPLE_RATE}Hz audio, got {sample_rate}Hz: {audio_path}")
    return torch.from_numpy(audio_data)


def transcribe_audio(
    model: WhisperModel,
    waveform: np.ndarray,
    speech_segments: list[dict],
    glossary: Glossary,
    beam_size: int = 5,
) -> dict:
    """Runs Faster-Whisper per segment, then glossary refinement on each resulting segment's text."""
    all_text_parts = []
    all_whisper_segments = []
    detected_language = None
    language_probability = None

    for vad_segment in speech_segments:
        clip = waveform[vad_segment["start_sample"]:vad_segment["end_sample"]]
        if clip.size == 0:
            continue

        try:
            segments, info = model.transcribe(clip, beam_size=beam_size)
            segments = list(segments)
        except Exception as error:
            raise RuntimeError(f"Transcription failed on segment {vad_segment}: {error}")

        if detected_language is None:
            detected_language = info.language
            language_probability = round(info.language_probability, 4)

        offset = vad_segment["start_seconds"]
        for seg in segments:
            corrected_text = glossary.apply(seg.text.strip())
            all_text_parts.append(corrected_text)
            all_whisper_segments.append({
                "start": round(offset + seg.start, 2),
                "end": round(offset + seg.end, 2),
                "text": corrected_text,
                "avg_logprob": round(seg.avg_logprob, 4),
                "no_speech_prob": round(seg.no_speech_prob, 4),
            })

    return {
        "text": " ".join(all_text_parts),
        "language": detected_language,
        "language_probability": language_probability,
        "speech_segments": speech_segments,
        "whisper_segments": all_whisper_segments,
    }


def merge_transcript_with_speakers(whisper_segments: list[dict], speaker_segments: list[dict]) -> list[dict]:
    """Attaches the speaker label with the greatest time overlap to each Whisper segment. No overlap -> 'Unknown'."""
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


def apply_teacher_verification(
    whisper_segments: list[dict],
    waveform: np.ndarray,
    teacher_verification_model,
    enrolled_teachers: list[tuple[str, list[float]]],
) -> list[dict]:
    """
    Slices the waveform per Whisper segment and labels each with
    is_teacher/teacher_name/confidence. Segments too short to embed
    reliably (<0.3s) are left unlabeled rather than guessed at.
    """
    labeled = []
    for segment in whisper_segments:
        start_sample = int(segment["start"] * SAMPLE_RATE)
        end_sample = int(segment["end"] * SAMPLE_RATE)
        clip = waveform[start_sample:end_sample]

        if clip.size < int(0.3 * SAMPLE_RATE):
            labeled.append({**segment, "is_teacher": False, "teacher_name": None, "confidence": 0.0})
            continue

        verification = teacher_verification_service.verify_segment(
            teacher_verification_model, clip, enrolled_teachers
        )
        labeled.append({**segment, **verification})
    return labeled


def run_pipeline(
    input_path: Path,
    models: LoadedModels,
    enable_denoise: bool = False,
    enable_vad: bool = True,
    enable_diarization: bool = False,
    enable_teacher_verification: bool = False,
    num_speakers: int | None = None,
    beam_size: int = 5,
    enrolled_teachers: list[tuple[str, list[float]]] | None = None,
) -> dict:
    """
    Full pipeline for one audio unit (a whole uploaded file, or one
    streamed chunk): ingest (always) -> denoise (toggle) -> VAD (toggle)
    -> transcribe + glossary -> diarize + merge (toggle) -> teacher
    verification (toggle). Returns everything session_service.py needs
    to append to a SessionRecord, including per-stage latencies.
    """
    if enable_diarization and models.diarization_model is None:
        raise ValueError("enable_diarization=True requires a loaded diarization_model.")
    if enable_teacher_verification and models.teacher_verification_model is None:
        raise ValueError("enable_teacher_verification=True requires a loaded teacher_verification_model.")

    timer = StageTimer()
    # Both declared before the try so the finally block can safely reference
    # them even if an exception hits before either is assigned (e.g.
    # ingest_audio itself raising) — see the finally block below for why
    # this cleanup can't just run after the last stage the way it used to.
    standardized_path: Path | None = None
    cleaned_path: Path | None = None

    try:
        with timer.track("preprocess"):
            standardized_path = ingest_audio(input_path, input_path.with_name(input_path.stem + "_std.wav"))

        with timer.track("denoise"):
            cleaned_path = clean_audio(standardized_path, enable_denoise)

        with timer.track("vad"):
            waveform, speech_segments = detect_speech(cleaned_path, enable_vad, models.silero_vad_model)

        with timer.track("transcribe"):
            result = transcribe_audio(models.whisper_model, waveform, speech_segments, models.glossary, beam_size)

        with timer.track("diarization"):
            if enable_diarization:
                raw_speaker_segments = diarization_service.diarize_audio(
                    models.diarization_model, cleaned_path, num_speakers=num_speakers
                )
                speaker_segments = diarization_service.format_speaker_segments(raw_speaker_segments)
                result["whisper_segments"] = merge_transcript_with_speakers(result["whisper_segments"], speaker_segments)
                result["speaker_segments"] = speaker_segments
            else:
                result["speaker_segments"] = []

        with timer.track("teacher_verification"):
            if enable_teacher_verification:
                result["whisper_segments"] = apply_teacher_verification(
                    result["whisper_segments"], waveform, models.teacher_verification_model, enrolled_teachers or []
                )

        result["stage_latencies"] = timer.latencies
        result["audio_duration_seconds"] = round(len(waveform) / SAMPLE_RATE, 2)
        return result
    finally:
        # In a finally, not just after the last stage succeeds: any
        # exception raised above (a corrupt chunk failing VAD, a transient
        # Whisper error, etc.) used to skip this entirely, leaking
        # standardized_path/cleaned_path to disk permanently — directly
        # contradicting CLAUDE.md's documented privacy property that temp
        # files are always cleaned up regardless of outcome. `input_path`
        # itself is the caller's temp file, not ours, and isn't touched here.
        if cleaned_path is not None and cleaned_path != standardized_path:
            cleaned_path.unlink(missing_ok=True)
        if standardized_path is not None:
            standardized_path.unlink(missing_ok=True)
