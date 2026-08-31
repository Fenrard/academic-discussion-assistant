from backend.services.minutes_service import generate_minutes


def _segment(start, end, text, speaker="Speaker A"):
    return {"start": start, "end": end, "text": text, "speaker": speaker}


def test_generate_minutes_groups_topics_by_time_gap():
    segments = [
        _segment(0.0, 2.0, "Let's start with fractions today."),
        _segment(2.0, 4.0, "Fractions are parts of a whole."),
        _segment(30.0, 32.0, "Now let's move to decimals."),
        _segment(32.0, 34.0, "Decimals are another way to write fractions."),
    ]
    minutes = generate_minutes(segments, keywords=["fractions", "decimals"], topic_gap_seconds=8.0)

    assert len(minutes["topics"]) == 2
    assert minutes["topics"][0]["start"] == 0.0
    assert minutes["topics"][1]["start"] == 30.0


def test_generate_minutes_detects_action_items():
    segments = [
        _segment(0.0, 2.0, "Today's lesson is about the water cycle."),
        _segment(2.0, 4.0, "Your assignment is due next Monday, don't forget."),
    ]
    minutes = generate_minutes(segments, keywords=["water cycle"])

    assert len(minutes["action_items"]) == 1
    assert "assignment" in minutes["action_items"][0]["text"].lower()


def test_generate_minutes_on_empty_segments():
    minutes = generate_minutes([], keywords=[])
    assert minutes["topics"] == []
    assert minutes["action_items"] == []
    assert minutes["duration_seconds"] == 0.0


def test_generate_minutes_lists_unique_participants_in_order():
    segments = [
        _segment(0.0, 1.0, "Hello class.", speaker="Speaker A"),
        _segment(1.0, 2.0, "Good morning.", speaker="Speaker B"),
        _segment(2.0, 3.0, "Let's begin.", speaker="Speaker A"),
    ]
    minutes = generate_minutes(segments, keywords=[])
    assert minutes["participants"] == ["Speaker A", "Speaker B"]
