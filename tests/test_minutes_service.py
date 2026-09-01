from backend.services.minutes_service import generate_minutes


def _segment(start, end, text, speaker="Speaker A", is_teacher=None):
    segment = {"start": start, "end": end, "text": text, "speaker": speaker}
    if is_teacher is not None:
        segment["is_teacher"] = is_teacher
    return segment


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
    assert minutes["definitions"] == []
    assert minutes["teacher_speech_ratio"] == 0.0
    assert minutes["teacher_speakers"] == []
    assert minutes["duration_seconds"] == 0.0


def test_generate_minutes_lists_unique_participants_in_order():
    segments = [
        _segment(0.0, 1.0, "Hello class.", speaker="Speaker A"),
        _segment(1.0, 2.0, "Good morning.", speaker="Speaker B"),
        _segment(2.0, 3.0, "Let's begin.", speaker="Speaker A"),
    ]
    minutes = generate_minutes(segments, keywords=[])
    assert minutes["participants"] == ["Speaker A", "Speaker B"]


# --- Teacher-speech prioritization (objective 2: "identify and prioritize instructional speech") ---

def test_key_points_prioritizes_teacher_segments_over_longer_non_teacher_ones():
    segments = [
        _segment(
            0.0, 2.0,
            "This is a much longer non-teacher comment about something unrelated to the lesson at hand.",
            speaker="Speaker A", is_teacher=False,
        ),
        _segment(2.0, 3.0, "Short teacher point.", speaker="Speaker B", is_teacher=True),
    ]
    minutes = generate_minutes(segments, keywords=[])
    key_points = minutes["topics"][0]["key_points"]
    assert key_points[0] == "Short teacher point."


def test_key_points_falls_back_to_length_when_no_teacher_data():
    # No is_teacher key on any segment (enable_teacher_verification was off) -> unchanged, original behavior.
    segments = [
        _segment(0.0, 2.0, "Short."),
        _segment(2.0, 3.0, "A somewhat longer segment of text."),
    ]
    minutes = generate_minutes(segments, keywords=[])
    key_points = minutes["topics"][0]["key_points"]
    assert key_points[0] == "A somewhat longer segment of text."


def test_label_topic_prefers_keyword_in_teacher_speech():
    segments = [
        _segment(0.0, 2.0, "Someone mentioned bananas randomly.", speaker="Speaker A", is_teacher=False),
        _segment(2.0, 4.0, "Today we discuss photosynthesis in detail.", speaker="Speaker B", is_teacher=True),
    ]
    # "bananas" is listed first, and appears in the block's non-teacher text — without
    # teacher prioritization it would win. With it, the teacher's "photosynthesis" wins.
    minutes = generate_minutes(segments, keywords=["bananas", "photosynthesis"])
    assert minutes["topics"][0]["label"] == "photosynthesis"


def test_teacher_speech_ratio():
    segments = [
        _segment(0.0, 3.0, "Teacher talking.", is_teacher=True),
        _segment(3.0, 4.0, "Student talking.", is_teacher=False),
    ]
    minutes = generate_minutes(segments, keywords=[])
    assert minutes["teacher_speech_ratio"] == 0.75


def test_teacher_speech_ratio_zero_without_teacher_data():
    segments = [_segment(0.0, 3.0, "Hello."), _segment(3.0, 4.0, "World.")]
    minutes = generate_minutes(segments, keywords=[])
    assert minutes["teacher_speech_ratio"] == 0.0


def test_teacher_speakers_identifies_majority_teacher_speaker():
    segments = [
        _segment(0.0, 5.0, "Teacher lecturing.", speaker="Speaker A", is_teacher=True),
        _segment(5.0, 6.0, "Student question.", speaker="Speaker B", is_teacher=False),
    ]
    minutes = generate_minutes(segments, keywords=[])
    assert minutes["teacher_speakers"] == ["Speaker A"]


# --- Definitions (objective 4: "key points, topics, definitions, and tasks") ---

def test_find_definitions_english():
    segments = [_segment(0.0, 5.0, "Photosynthesis is a process that plants use to make food from sunlight.")]
    minutes = generate_minutes(segments, keywords=[])
    definitions = minutes["definitions"]
    assert len(definitions) == 1
    assert definitions[0]["term"] == "Photosynthesis"
    assert "process" in definitions[0]["definition"]


def test_find_definitions_filipino():
    segments = [_segment(0.0, 5.0, "Fotosintesis ay isang proseso na ginagamit ng mga halaman upang gumawa ng pagkain.")]
    minutes = generate_minutes(segments, keywords=[])
    terms = [d["term"] for d in minutes["definitions"]]
    assert "Fotosintesis" in terms


def test_find_definitions_hiligaynon():
    segments = [_segment(0.0, 5.0, "Fotosintesis amo ang proseso nga ginagamit sang mga tanom.")]
    minutes = generate_minutes(segments, keywords=[])
    terms = [d["term"] for d in minutes["definitions"]]
    assert "Fotosintesis" in terms


def test_find_definitions_dedups_repeated_terms():
    segments = [
        _segment(0.0, 5.0, "Photosynthesis is a process that plants use to make food."),
        _segment(5.0, 10.0, "Photosynthesis is a completely different explanation here too."),
    ]
    minutes = generate_minutes(segments, keywords=[])
    terms = [d["term"] for d in minutes["definitions"]]
    assert terms.count("Photosynthesis") == 1


def test_find_definitions_tags_speaker_and_teacher_flag():
    segments = [_segment(0.0, 5.0, "Photosynthesis is a process plants use.", speaker="Speaker A", is_teacher=True)]
    minutes = generate_minutes(segments, keywords=[])
    assert minutes["definitions"][0]["speaker"] == "Speaker A"
    assert minutes["definitions"][0]["is_teacher"] is True


def test_find_definitions_empty_when_no_definitional_language():
    segments = [_segment(0.0, 2.0, "Hello everyone, welcome to class.")]
    minutes = generate_minutes(segments, keywords=[])
    assert minutes["definitions"] == []
