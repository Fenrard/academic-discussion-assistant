"""
Rule-based structured minutes generation (CLAUDE.md: "Minutes generation
| Rule-based structured output" — deliberately not an LLM/abstractive
summarizer). Turns merged transcript segments + TextRank keywords into:

  - topic blocks (grouped by time-gap between segments)
  - key points per topic (teacher-labeled segments ranked first, then
    longest-first — "prioritize instructional speech" applied to minutes,
    not just to the raw is_teacher label on each segment)
  - definitions (heuristic trilingual pattern matching)
  - action items (heuristic trigger-phrase matching, trilingual)
  - participants + which of them was majority-teacher-speech
  - teacher_speech_ratio (fraction of total duration that was the teacher)

This is a heuristic, not an NLP model — it will miss/misfire on real
classroom audio. Good enough for a functional prototype; not claimed to
be more than that. Every "prioritize the teacher" behavior here is a
no-op when segments carry no is_teacher label at all (i.e.
enable_teacher_verification was off for the session) — it degrades to
the original behavior, it doesn't break.
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

# Definitional constructs, trilingual. The article ("a/an/the", "isa/isang", "ang/isa
# ka") after the copula is what keeps the English/Filipino/Hiligaynon "is" patterns
# from matching every ordinary sentence that happens to contain "is" — a real,
# deliberate precision-over-recall tradeoff, same spirit as _ACTION_PATTERN. This is
# pattern matching, not NLP: it will miss definitions phrased unusually, and can
# still false-positive on a sentence that isn't actually defining anything. Needs
# real classroom audio to actually measure precision/recall — see evaluation/wer.py's
# sibling scripts once that data exists.
_TERM = r"([A-Z][A-Za-z0-9\-]*(?:\s+[A-Za-z0-9\-]+){0,4})"
_LOWER_TERM = r"([A-Za-z0-9\-]+(?:\s+[A-Za-z0-9\-]+){0,4})"
_DEF = r"([^.!?]{5,200})"
_DEFINITION_PATTERNS = [
    # English
    re.compile(rf"\b{_TERM}\s+(?:is|are)\s+(?:a|an|the)\s+{_DEF}"),
    re.compile(rf"\b{_TERM}\s+(?:means|refers to|is defined as|is called)\s+{_DEF}", re.IGNORECASE),
    # Filipino: "<Term> ay isa/isang <definition>", "ibig sabihin ng <Term> ay <definition>"
    re.compile(rf"\b{_TERM}\s+ay\s+(?:isang|isa)\s+{_DEF}"),
    re.compile(rf"ibig sabihin ng\s+{_LOWER_TERM}\s+ay\s+{_DEF}", re.IGNORECASE),
    # Hiligaynon: "<Term> amo ang/isa ka <definition>", "buot silingon sang/ni <Term> amo <definition>"
    re.compile(rf"\b{_TERM}\s+amo\s+(?:ang|isa ka)\s+{_DEF}"),
    re.compile(rf"buot silingon (?:sang|ni)\s+{_LOWER_TERM}\s+amo\s+{_DEF}", re.IGNORECASE),
]
_MAX_TERM_WORDS = 5


def _is_teacher(segment: dict) -> bool:
    return bool(segment.get("is_teacher"))


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
    """
    Prefers a keyword match within teacher speech first — the topic label
    should reflect what was taught, not whichever student aside happened
    to share a word with the keyword list. Falls back to the whole block
    when there's no teacher speech in it (or no teacher-verification data
    at all, in which case teacher_text is always empty and this behaves
    exactly like the original single-pass version).
    """
    teacher_text = " ".join(seg["text"].lower() for seg in block if _is_teacher(seg))
    block_text = " ".join(seg["text"].lower() for seg in block)

    for keyword in keywords:
        if keyword.lower() in teacher_text:
            return keyword
    for keyword in keywords:
        if keyword.lower() in block_text:
            return keyword

    # Fallback: first few words of the block.
    first_words = block[0]["text"].strip().split()
    return " ".join(first_words[:6]) or "Untitled topic"


def _key_points(block: list[dict], max_points: int = 3) -> list[str]:
    """
    Teacher-labeled segments rank ahead of everyone else's regardless of
    length, then longest-first within each group — instructional content
    is what "prioritize instructional speech" means for minutes, not just
    whoever talked the longest. A no-op (pure length sort, same as before)
    when nothing in the block carries an is_teacher label.
    """
    ranked = sorted(block, key=lambda seg: (_is_teacher(seg), len(seg["text"])), reverse=True)
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


def _find_definitions(segments: list[dict]) -> list[dict]:
    """One entry per distinct term (first mention wins), tagged with who said it."""
    definitions: list[dict] = []
    seen_terms: set[str] = set()

    for segment in segments:
        text = segment.get("text", "").strip()
        if not text:
            continue

        for pattern in _DEFINITION_PATTERNS:
            for match in pattern.finditer(text):
                term = match.group(1).strip().strip(",")
                definition = match.group(2).strip().strip(",")
                key = term.lower()

                if not term or not definition or key in seen_terms:
                    continue
                if len(term.split()) > _MAX_TERM_WORDS:
                    continue

                seen_terms.add(key)
                definitions.append({
                    "term": term,
                    "definition": definition,
                    "start": segment["start"],
                    "speaker": segment.get("speaker", "Unknown"),
                    "is_teacher": segment.get("is_teacher"),
                })

    return definitions


def _participants(segments: list[dict]) -> list[str]:
    seen: list[str] = []
    for segment in segments:
        speaker = segment.get("speaker", "Unknown")
        if speaker not in seen:
            seen.append(speaker)
    return seen


def _teacher_speech_ratio(segments: list[dict]) -> float:
    """
    Fraction of total speech duration attributed to the teacher. 0.0 both
    when the teacher genuinely didn't speak AND when enable_teacher_verification
    was off for the session (no is_teacher labels exist to sum) — this field
    is only meaningful to read when at least one segment carries the label.
    """
    if not segments:
        return 0.0
    total_duration = sum(seg["end"] - seg["start"] for seg in segments)
    if total_duration <= 0:
        return 0.0
    teacher_duration = sum(seg["end"] - seg["start"] for seg in segments if _is_teacher(seg))
    return round(teacher_duration / total_duration, 4)


def _teacher_speakers(segments: list[dict]) -> list[str]:
    """Which diarized speaker labels (Speaker A, B, ...) were majority-teacher by duration."""
    duration_by_speaker: dict[str, float] = {}
    teacher_duration_by_speaker: dict[str, float] = {}
    order: list[str] = []

    for segment in segments:
        speaker = segment.get("speaker", "Unknown")
        if speaker not in order:
            order.append(speaker)
        duration = segment["end"] - segment["start"]
        duration_by_speaker[speaker] = duration_by_speaker.get(speaker, 0.0) + duration
        if _is_teacher(segment):
            teacher_duration_by_speaker[speaker] = teacher_duration_by_speaker.get(speaker, 0.0) + duration

    return [
        speaker for speaker in order
        if teacher_duration_by_speaker.get(speaker, 0.0) > duration_by_speaker[speaker] / 2
    ]


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
        "teacher_speech_ratio": _teacher_speech_ratio(segments),
        "teacher_speakers": _teacher_speakers(segments),
        "keywords": keywords,
        "topics": topics,
        "definitions": _find_definitions(segments),
        "action_items": _find_action_items(segments),
    }
