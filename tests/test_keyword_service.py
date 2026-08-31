from backend.services.keyword_service import extract_keywords


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
