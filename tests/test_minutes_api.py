"""
backend/api/minutes.py's `_render_minutes()` — the markdown/txt export
formatter — had zero direct test coverage before this file: it's a pure
function of (title, minutes dict, as_markdown), no DB/auth/HTTP needed to
exercise it directly.
"""

from backend.api.minutes import _render_minutes

_BASE_MINUTES = {
    "generated_at": "2026-09-01T10:05:00Z",
    "duration_seconds": 600.0,
    "participants": ["Teacher", "Speaker A"],
    "keywords": ["algebra"],
    "topics": [],
    "definitions": [],
    "action_items": [],
}


def test_teacher_speech_line_included_when_ratio_is_a_genuine_zero():
    # Regression test: `if teacher_ratio:` treated a real, computed 0.0 the
    # same as the field being absent (an older session, or verification
    # never having run), silently dropping the line instead of reporting
    # "the teacher genuinely didn't speak" -- a meaningfully different fact.
    minutes = {**_BASE_MINUTES, "teacher_speech_ratio": 0.0, "teacher_speakers": []}
    body = _render_minutes("Lecture 1", minutes, as_markdown=False)
    assert "Teacher speech: 0.0%" in body


def test_teacher_speech_line_omitted_when_verification_never_ran():
    minutes = {**_BASE_MINUTES}  # no teacher_speech_ratio key at all
    body = _render_minutes("Lecture 1", minutes, as_markdown=False)
    assert "Teacher speech" not in body


def test_teacher_speech_line_included_for_a_nonzero_ratio():
    minutes = {**_BASE_MINUTES, "teacher_speech_ratio": 0.62, "teacher_speakers": ["Speaker A"]}
    body = _render_minutes("Lecture 1", minutes, as_markdown=False)
    assert "Teacher speech: 62.0% (Speaker A)" in body
