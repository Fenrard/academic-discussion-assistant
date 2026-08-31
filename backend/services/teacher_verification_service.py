"""
SpeechBrain ECAPA-TDNN teacher verification — the critical-path item
CLAUDE.md marks unbuilt. Enrollment stores one embedding per teacher;
verification compares a speaker segment's embedding against every
enrolled teacher by cosine similarity and labels the segment
teacher/non-teacher if the best match clears the threshold.

Lazy-imports speechbrain, same pattern process_pipeline.py already uses
for pyrnnoise: a missing/failed install raises a clean RuntimeError
instead of crashing the whole backend at import time, and
enable_teacher_verification defaults to False so nothing downstream
depends on it being present.
"""

import numpy as np

from backend.core.config import settings


def load_verification_model():
    """Loads the SpeechBrain ECAPA-TDNN speaker-embedding model once, at startup."""
    try:
        from speechbrain.inference.speaker import EncoderClassifier
    except ImportError:
        raise RuntimeError(
            "speechbrain is not installed. Install with 'pip install speechbrain', "
            "or call with enable_teacher_verification=False to skip this stage."
        )

    try:
        return EncoderClassifier.from_hparams(
            source=settings.speaker_verification_model,
            savedir=f"models/{settings.speaker_verification_model.replace('/', '_')}",
        )
    except Exception as error:
        raise RuntimeError(f"Failed to load speaker verification model: {error}")


def extract_embedding(model, waveform: np.ndarray) -> list[float]:
    """
    waveform: mono float32 samples at 16kHz. Returns the ECAPA embedding
    as a plain list[float] so it's directly JSON-serializable for storage.
    """
    import torch

    if waveform.size == 0:
        raise ValueError("Cannot extract an embedding from an empty audio clip.")

    tensor = torch.from_numpy(waveform).float().unsqueeze(0)
    with torch.no_grad():
        embedding = model.encode_batch(tensor)

    return embedding.squeeze().detach().cpu().numpy().tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    vector_a, vector_b = np.array(a), np.array(b)
    denominator = np.linalg.norm(vector_a) * np.linalg.norm(vector_b)
    if denominator == 0:
        return 0.0
    return float(np.dot(vector_a, vector_b) / denominator)


def verify_segment(
    model,
    waveform_slice: np.ndarray,
    enrolled_teachers: list[tuple[str, list[float]]],
    threshold: float | None = None,
) -> dict:
    """
    Returns {"is_teacher": bool, "teacher_name": str | None, "confidence": float}
    for one audio slice (e.g. one diarized speaker turn), by cosine
    similarity against every enrolled teacher embedding — best match wins.
    """
    similarity_threshold = threshold if threshold is not None else settings.teacher_verification_threshold

    if not enrolled_teachers:
        return {"is_teacher": False, "teacher_name": None, "confidence": 0.0}

    segment_embedding = extract_embedding(model, waveform_slice)

    best_name, best_score = None, -1.0
    for name, enrolled_embedding in enrolled_teachers:
        score = cosine_similarity(segment_embedding, enrolled_embedding)
        if score > best_score:
            best_name, best_score = name, score

    is_teacher = best_score >= similarity_threshold
    return {
        "is_teacher": is_teacher,
        "teacher_name": best_name if is_teacher else None,
        "confidence": round(best_score, 4),
    }
