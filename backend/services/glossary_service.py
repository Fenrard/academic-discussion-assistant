"""
Glossary-based post-processing for the Hiligaynon/Filipino/English
trilingual output ("Post-processing | Glossary-based refinement" in
CLAUDE.md's tech stack table). Applied per-chunk, right after Whisper
transcription and before a chunk result is returned/stored, so the
growing transcript Flutter sees is already corrected in real time.

`backend/data/glossary.json` is a starter list (see its "_meta" field) —
this module only does the matching/replacement mechanics, and is
correct regardless of how many entries the glossary ends up with.
"""

import json
import re
from pathlib import Path

from backend.core.config import settings


class Glossary:
    def __init__(self, terms: dict[str, str]):
        # Drop empty/whitespace-only keys before anything else: an empty key
        # escapes to an empty regex alternative, and `\b(?:)\b` matches the
        # zero-width position at every word boundary — sub() would then splice
        # the replacement in all over the text. A stray "" in a hand-edited
        # glossary.json is absurd but shouldn't be able to corrupt every transcript.
        terms = {key: value for key, value in terms.items() if key and key.strip()}
        # Longest phrase first, so multi-word entries match before any
        # single-word entry inside them would.
        ordered_keys = sorted(terms.keys(), key=len, reverse=True)
        # Keyed lowercase, matching how _replace_match looks them up (the
        # match is case-insensitive) — backend/data/glossary.json's own
        # "_meta" field documents lowercase keys as a convention, but that
        # was never enforced here: a mixed-case key raised KeyError on every
        # match. Lowercasing here makes the class correct regardless of the
        # JSON file's own casing.
        self._replacements = {key.lower(): terms[key] for key in ordered_keys}
        pattern = "|".join(re.escape(key) for key in ordered_keys)
        self._compiled = re.compile(rf"\b(?:{pattern})\b", re.IGNORECASE) if ordered_keys else None

    def apply(self, text: str) -> str:
        """Case-insensitive match, case-preserving replacement."""
        if not text or self._compiled is None:
            return text
        return self._compiled.sub(self._replace_match, text)

    def _replace_match(self, match: re.Match) -> str:
        matched_text = match.group(0)
        replacement = self._replacements[matched_text.lower()]

        if matched_text.isupper():
            return replacement.upper()
        if matched_text[0].isupper():
            return replacement[0].upper() + replacement[1:]
        return replacement


def load_glossary(glossary_path: Path | None = None) -> Glossary:
    """Loads backend/data/glossary.json into a Glossary. Missing/empty file -> no-op glossary."""
    path = glossary_path or settings.glossary_path
    if not path.exists():
        return Glossary({})

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Malformed glossary file at '{path}': {error}")
    except UnicodeDecodeError as error:
        # The glossary is meant to be grown by hand from the corpus pass;
        # a Windows editor saving it as ANSI/cp1252 with a Hiligaynon
        # character would otherwise crash worker startup with a bare
        # UnicodeDecodeError (it's a ValueError, not a JSONDecodeError).
        raise RuntimeError(f"Glossary file at '{path}' is not valid UTF-8 — re-save it as UTF-8. ({error})")

    return Glossary(data.get("terms", {}))
