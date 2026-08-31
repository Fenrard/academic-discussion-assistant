"""
WER and CER against reference transcripts (CLAUDE.md build-priority
#11: evaluation/wer.py). Implemented as a from-scratch DP edit-distance
rather than pulling in `jiwer` — the algorithm is ~20 lines and this
keeps evaluation/ dependency-free beyond what's already installed.

Metrics: overall WER/CER (evaluation/wer.py's core job), plus a
by-group breakdown hook (compute_error_rates_by_group) for CLAUDE.md's
"WER/CER... broken out by language segment" and "code-switched
utterances reported separately" requirements — group labels (language,
or "code-switched" vs "monolingual") are supplied by the caller/manual
annotation, since Whisper doesn't yet tag output per-segment by
language (see CLAUDE.md's "Known Open Issues").

No argparse/CLI concerns inside the importable functions — main() is a
thin wrapper, same convention as scripts/.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPORTS_DIR = Path(__file__).resolve().parent / "reports"

_PUNCTUATION_PATTERN = re.compile(r"[^\w\s']", re.UNICODE)


def normalize_text(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace — applied before both WER and CER."""
    text = _PUNCTUATION_PATTERN.sub("", text.lower())
    return " ".join(text.split())


def _edit_distance(reference: list, hypothesis: list) -> int:
    """Classic Levenshtein DP over a token or character sequence."""
    rows, cols = len(reference) + 1, len(hypothesis) + 1
    distances = [[0] * cols for _ in range(rows)]

    for i in range(rows):
        distances[i][0] = i
    for j in range(cols):
        distances[0][j] = j

    for i in range(1, rows):
        for j in range(1, cols):
            if reference[i - 1] == hypothesis[j - 1]:
                distances[i][j] = distances[i - 1][j - 1]
            else:
                distances[i][j] = 1 + min(
                    distances[i - 1][j],      # deletion
                    distances[i][j - 1],      # insertion
                    distances[i - 1][j - 1],  # substitution
                )

    return distances[-1][-1]


def word_error_rate(reference: str, hypothesis: str) -> float:
    """WER = edit distance over word tokens / word count of reference. Empty reference -> 0.0 if hypothesis is also empty, else 1.0."""
    ref_words = normalize_text(reference).split()
    hyp_words = normalize_text(hypothesis).split()

    if not ref_words:
        return 0.0 if not hyp_words else 1.0

    return round(_edit_distance(ref_words, hyp_words) / len(ref_words), 4)


def character_error_rate(reference: str, hypothesis: str) -> float:
    """CER = edit distance over characters (spaces included) / character count of reference."""
    ref_chars = list(normalize_text(reference))
    hyp_chars = list(normalize_text(hypothesis))

    if not ref_chars:
        return 0.0 if not hyp_chars else 1.0

    return round(_edit_distance(ref_chars, hyp_chars) / len(ref_chars), 4)


def compute_error_rates(reference: str, hypothesis: str) -> dict:
    return {
        "wer": word_error_rate(reference, hypothesis),
        "cer": character_error_rate(reference, hypothesis),
        "reference_word_count": len(normalize_text(reference).split()),
    }


def compute_error_rates_by_group(pairs: list[tuple[str, str]], groups: list[str]) -> dict:
    """
    pairs: [(reference_text, hypothesis_text), ...] aligned 1:1 with groups
    (e.g. groups=["english", "hiligaynon", "code-switched", ...]).
    Returns per-group aggregate WER/CER plus the overall figure.
    """
    if len(pairs) != len(groups):
        raise ValueError(f"pairs and groups must be the same length, got {len(pairs)} and {len(groups)}.")

    by_group: dict[str, list[dict]] = {}
    for (reference, hypothesis), group in zip(pairs, groups):
        by_group.setdefault(group, []).append(compute_error_rates(reference, hypothesis))

    def _average(entries: list[dict], key: str) -> float:
        return round(sum(entry[key] for entry in entries) / len(entries), 4) if entries else 0.0

    report = {
        group: {
            "wer": _average(entries, "wer"),
            "cer": _average(entries, "cer"),
            "utterance_count": len(entries),
        }
        for group, entries in by_group.items()
    }

    all_reference = " ".join(ref for ref, _ in pairs)
    all_hypothesis = " ".join(hyp for _, hyp in pairs)
    report["overall"] = compute_error_rates(all_reference, all_hypothesis)

    return report


def write_report(report: dict, label: str = "wer") -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = REPORTS_DIR / f"{label}_{timestamp}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report_path


def main() -> None:
    """CLI entry point: compare two plain-text transcript files."""
    parser = argparse.ArgumentParser(description="Compute WER/CER between a reference and hypothesis transcript.")
    parser.add_argument("reference_file", type=str, help="Path to the ground-truth transcript (.txt).")
    parser.add_argument("hypothesis_file", type=str, help="Path to the pipeline's output transcript (.txt).")
    args = parser.parse_args()

    reference_path = Path(args.reference_file).resolve()
    hypothesis_path = Path(args.hypothesis_file).resolve()

    try:
        reference_text = reference_path.read_text(encoding="utf-8")
        hypothesis_text = hypothesis_path.read_text(encoding="utf-8")
    except OSError as error:
        print(f"Error: {error}")
        sys.exit(1)

    result = compute_error_rates(reference_text, hypothesis_text)
    report_path = write_report({"reference_file": str(reference_path), "hypothesis_file": str(hypothesis_path), **result})

    print(f"WER: {result['wer']}")
    print(f"CER: {result['cer']}")
    print(f"Reference word count: {result['reference_word_count']}")
    print(f"Report written to: {report_path}")


if __name__ == "__main__":
    main()
