"""
Backend-service copy of scripts/diarize_audio.py's importable functions
(load_diarization_model, diarize_audio, format_speaker_segments) — same
logic and signatures, documented in CLAUDE.md's function-signature
reference table. scripts/diarize_audio.py itself stays untouched (dev
utility); this is the version audio_service.py actually calls, loaded
once at FastAPI startup and passed in like every other model here.
"""

from pathlib import Path

from pyannote.audio import Pipeline

PIPELINE_NAME = "pyannote/speaker-diarization-community-1"


def load_diarization_model(hf_token: str | None) -> Pipeline:
    if not hf_token:
        raise RuntimeError(
            "No Hugging Face token provided. Create one at "
            "https://huggingface.co/settings/tokens and set the HF_TOKEN "
            "environment variable, or call with enable_diarization=False to skip this stage."
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
    if not audio_path.exists():
        raise FileNotFoundError(f"No audio file found at: {audio_path}")

    try:
        kwargs = {"num_speakers": num_speakers} if num_speakers else {}
        output = pipeline(str(audio_path), **kwargs)
    except Exception as error:
        raise RuntimeError(f"Diarization failed on '{audio_path.name}': {error}")

    # community-1's Pipeline.__call__ returns a DiarizeOutput dataclass whose
    # `.speaker_diarization` is a pyannote Annotation; older 3.x pipelines
    # return a bare Annotation. Either way, iterate it with itertracks(
    # yield_label=True) -> (segment, track, label) — matching pyannote's own
    # DiarizeOutput.serialize(). The previous `for turn, speaker in
    # output.speaker_diarization` unpacked each Segment (a 2-tuple of floats)
    # into (turn, speaker) and then `turn.start` blew up with AttributeError
    # on every real diarization run (untested — needs the gated model).
    annotation = getattr(output, "speaker_diarization", output)
    return [
        (turn.start, turn.end, speaker)
        for turn, _track, speaker in annotation.itertracks(yield_label=True)
    ]


def format_speaker_segments(raw_segments: list[tuple]) -> list[dict]:
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
    letters = ""
    index += 1
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters
