import sys

import pytest

from evaluation.wer import character_error_rate, compute_error_rates_by_group, main, word_error_rate


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


def test_main_reports_a_clean_error_on_a_non_utf8_transcript_file(tmp_path, monkeypatch, capsys):
    # Regression test: a human typing a reference transcript on Windows can
    # easily save it in the system ANSI codepage (Notepad's historical
    # default) rather than UTF-8. UnicodeDecodeError is a ValueError
    # subclass, not an OSError, so `except OSError` let it fall straight
    # through as an unhandled traceback instead of the same clean
    # "Error: ..." + exit(1) every other bad-input path here gets.
    reference_path = tmp_path / "reference.txt"
    hypothesis_path = tmp_path / "hypothesis.txt"
    reference_path.write_bytes("kumusta ka, guro? — na-miss ka namon.".encode("cp1252"))
    hypothesis_path.write_text("kumusta ka guro", encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["wer.py", str(reference_path), str(hypothesis_path)])
    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 1
    assert "utf-8" in capsys.readouterr().out.lower()
