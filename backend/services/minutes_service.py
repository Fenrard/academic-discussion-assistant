"""
Rule-based structured minutes generation (CLAUDE.md: "Minutes generation
| Rule-based structured output" — deliberately not an LLM/abstractive
summarizer). Turns merged transcript segments + TextRank keywords into:

  - topic blocks (grouped by time-gap between segments)
  - key points per topic (longest segment(s) in that block)
  - action items (heuristic trigger-phrase matching, trilingual)
  - participants (unique speaker labels, teacher flag if present)

This is a heuristic, not an NLP model — it will miss/misfire on real
classroom audio. Good enough for a functional prototype; not claimed to
be more than that.
"""

import re
from datetime import datetime, timezone

from backend.core.config import settings

_ACTION_TRIGGERS = [
    # English
    r"\bassignment\b", r"\bhomework\b", r"\bdue\b", r"\bsubmit\b", r"\breminder\b",
    r"don'?t forget", r"remember to", r"next meeting", r"\brequirement\b", r"\bquiz\b",
    r"\bexam\b", r"\bproject\b", r"\bdeadline\b",
    # Filipino
    r"\bpasahan\b", r"\bipasa\b", r"\btandaan\b", r"\bgawin\s+n?yo\b", r"\bbukas\b",
    r"\brequirement\b",
    # Hiligaynon
    r"\bihatag\b", r"\bdumdumon\b", r"\bbuhaton\b", r"\bipasa\b",
]
_ACTION_PATTERN = re.compile("|".join(_ACTION_TRIGGERS), re.IGNORECASE)


def _group_into_topics(segments: list[dict], gap_seconds: float) -> list[list[dict]]:
    if not segments:
        return []

    ordered = sorted(segments, key=lambda s: s["start"])
    blocks: list[list[dict]] = [[ordered[0]]]

    for segment in ordered[1:]:
        previous_end = blocks[-1][-1]["end"]
        if segment["start"] - previous_end > gap_seconds:
            blocks.append([segment])
        else:
            blocks[-1].append(segment)

    return blocks


def _label_topic(block: list[dict], keywords: list[str]) -> str:
    block_text = " ".join(seg["text"].lower() for seg in block)
    for keyword in keywords:
        if keyword.lower() in block_text:
            return keyword
    # Fallback: first few words of the block.
    first_words = block[0]["text"].strip().split()
    return " ".join(first_words[:6]) or "Untitled topic"


def _key_points(block: list[dict], max_points: int = 3) -> list[str]:
    ranked = sorted(block, key=lambda seg: len(seg["text"]), reverse=True)
    return [seg["text"].strip() for seg in ranked[:max_points] if seg["text"].strip()]


def _find_action_items(segments: list[dict]) -> list[dict]:
    action_items = []
    for segment in segments:
        text = segment.get("text", "")
        if _ACTION_PATTERN.search(text):
            action_items.append({
                "text": text.strip(),
                "start": segment["start"],
                "speaker": segment.get("speaker", "Unknown"),
            })
    return action_items


def _participants(segments: list[dict]) -> list[str]:
    seen: list[str] = []
    for segment in segments:
        speaker = segment.get("speaker", "Unknown")
        if speaker not in seen:
            seen.append(speaker)
    return seen


def generate_minutes(
    segments: list[dict],
    keywords: list[str],
    topic_gap_seconds: float | None = None,
) -> dict:
    """
    Builds the structured minutes dict stored on SessionRecord.minutes
    and returned by GET /sessions/{id}/minutes.
    """
    gap = topic_gap_seconds if topic_gap_seconds is not None else settings.topic_gap_seconds
    blocks = _group_into_topics(segments, gap)

    topics = [
        {
            "label": _label_topic(block, keywords),
            "start": block[0]["start"],
            "end": block[-1]["end"],
            "key_points": _key_points(block),
        }
        for block in blocks
    ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(segments[-1]["end"], 2) if segments else 0.0,
        "participants": _participants(segments),
        "keywords": keywords,
        "topics": topics,
        "action_items": _find_action_items(segments),
    }
