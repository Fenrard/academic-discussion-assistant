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
