from backend.services.glossary_service import Glossary


def test_apply_replaces_case_insensitively():
    glossary = Glossary({"ilonggo": "Ilonggo"})
    # Matching is case-insensitive; an all-caps match stays all-caps in the
    # replacement (case is *preserved*, not forced to the glossary's canonical form).
    assert glossary.apply("she speaks ilonggo fluently.") == "she speaks Ilonggo fluently."
    assert glossary.apply("She speaks ILONGGO fluently.") == "She speaks ILONGGO fluently."


def test_apply_preserves_capitalization_of_match():
    glossary = Glossary({"amo ba": "amo bala"})
    assert glossary.apply("Amo ba gid?") == "Amo bala gid?"
    assert glossary.apply("amo ba gid?") == "amo bala gid?"


def test_apply_respects_word_boundaries():
    glossary = Glossary({"sir": "Sir"})
    # "sirena" should not become "Sirena" via a bare substring match.
    assert glossary.apply("sirena ka gid") == "sirena ka gid"


def test_apply_prefers_longest_match():
    glossary = Glossary({"ma am": "ma'am", "ma": "MA"})
    assert glossary.apply("Yes ma am") == "Yes ma'am"


def test_empty_glossary_is_a_no_op():
    glossary = Glossary({})
    assert glossary.apply("unchanged text") == "unchanged text"


def test_apply_handles_empty_text():
    glossary = Glossary({"ilonggo": "Ilonggo"})
    assert glossary.apply("") == ""


def test_empty_or_whitespace_keys_are_ignored_not_matched_everywhere():
    # Regression: an "" key escapes to an empty regex alternative, and
    # `\b(?:...|)\b` matches the zero-width position at every word boundary,
    # so sub() would splice the replacement in all over the text.
    glossary = Glossary({"": "BOOM", "   ": "BOOM", "ilonggo": "Ilonggo"})
    assert glossary.apply("she speaks ilonggo daily") == "she speaks Ilonggo daily"
    assert "BOOM" not in glossary.apply("plain sentence with no glossary terms")


def test_apply_does_not_crash_on_a_mixed_case_glossary_key():
    # Regression test: _replacements used to keep the JSON's original-case
    # keys while _replace_match looked them up lowercased, so any key that
    # wasn't already all-lowercase raised KeyError on every match — even
    # though matching itself is (correctly) case-insensitive.
    glossary = Glossary({"Sir Ko": "sir ko"})
    # Match starts uppercase -> replacement's first letter is forced uppercase.
    assert glossary.apply("He said Sir Ko to me.") == "He said Sir ko to me."
    # Match is all-lowercase -> replacement returned verbatim in its own casing.
    assert glossary.apply("He said sir ko to me.") == "He said sir ko to me."
