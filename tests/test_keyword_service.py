from backend.services.keyword_service import build_weighted_text, extract_keywords


def test_extract_keywords_returns_relevant_terms():
    text = (
        "The teacher explained photosynthesis today. Photosynthesis is how plants "
        "make food using sunlight. The class discussed photosynthesis for an hour "
        "and asked questions about photosynthesis and sunlight."
    )
    keywords = extract_keywords(text, top_n=5)
    assert keywords, "expected at least one keyword"
    assert any("photosynthesis" in keyword for keyword in keywords)


def test_extract_keywords_on_short_text_returns_empty():
    assert extract_keywords("Okay.", top_n=5) == []


def test_extract_keywords_on_empty_text_returns_empty():
    assert extract_keywords("", top_n=5) == []


def test_extract_keywords_respects_top_n():
    text = " ".join(f"topic{i} discussion classroom lesson" for i in range(20))
    keywords = extract_keywords(text, top_n=3)
    assert len(keywords) <= 3


# --- build_weighted_text (objective 2: prioritize instructional speech in keyword extraction) ---

def test_build_weighted_text_repeats_teacher_segments():
    segments = [
        {"text": "hello", "is_teacher": True},
        {"text": "world", "is_teacher": False},
    ]
    weighted = build_weighted_text(segments, teacher_weight=3)
    assert weighted.split().count("hello") == 3
    assert weighted.split().count("world") == 1


def test_build_weighted_text_is_noop_without_teacher_labels():
    # No "is_teacher" key at all -> identical to a plain join, same as before this existed.
    segments = [{"text": "hello"}, {"text": "world"}]
    assert build_weighted_text(segments) == "hello world"


def test_build_weighted_text_skips_empty_text():
    segments = [{"text": "   ", "is_teacher": True}, {"text": "real text"}]
    assert build_weighted_text(segments) == "real text"


def test_build_weighted_text_on_empty_segments():
    assert build_weighted_text([]) == ""
