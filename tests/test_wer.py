from evaluation.wer import character_error_rate, compute_error_rates_by_group, word_error_rate


def test_word_error_rate_identical_transcripts():
    assert word_error_rate("the quick brown fox", "the quick brown fox") == 0.0


def test_word_error_rate_one_substitution():
    # 1 substitution out of 4 reference words.
    assert word_error_rate("the quick brown fox", "the slow brown fox") == 0.25


def test_word_error_rate_is_case_and_punctuation_insensitive():
    assert word_error_rate("The Quick, Brown Fox!", "the quick brown fox") == 0.0


def test_word_error_rate_empty_reference_and_hypothesis():
    assert word_error_rate("", "") == 0.0


def test_word_error_rate_empty_reference_nonempty_hypothesis():
    assert word_error_rate("", "hello") == 1.0


def test_character_error_rate_identical_transcripts():
    assert character_error_rate("hiligaynon", "hiligaynon") == 0.0


def test_character_error_rate_one_typo():
    assert character_error_rate("hiligaynon", "hiligaynan") == round(1 / 10, 4)


def test_compute_error_rates_by_group():
    pairs = [
        ("kumusta ka", "kumusta ka"),          # perfect
        ("thank you very much", "thank you"),  # 2 deletions out of 4 words
    ]
    groups = ["hiligaynon", "english"]
    report = compute_error_rates_by_group(pairs, groups)

    assert report["hiligaynon"]["wer"] == 0.0
    assert report["english"]["wer"] == 0.5
    assert "overall" in report


def test_compute_error_rates_by_group_mismatched_lengths_raises():
    try:
        compute_error_rates_by_group([("a", "a")], ["one", "two"])
        assert False, "expected ValueError"
    except ValueError:
        pass
