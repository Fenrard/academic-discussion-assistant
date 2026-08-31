"""
System Usability Scale scoring (CLAUDE.md's Evaluation Metrics list:
"Usability | System Usability Scale (SUS) with actual respondents").

This module only does the scoring arithmetic — it cannot collect real
respondents for you. Standard 10-item SUS (Brooke, 1996): odd items
(1,3,5,7,9) are positively worded, even items (2,4,6,8,10) are
negatively worded, each answered on a 1-5 Likert scale (Strongly
Disagree..Strongly Agree). Adjective-rating bands are Bangor, Kortum &
Miller's (2009) commonly-cited SUS interpretation, not this project's
own invention.
"""

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

REPORTS_DIR = Path(__file__).resolve().parent / "reports"
ITEM_COUNT = 10

SUS_ITEMS = [
    "I think that I would like to use this system frequently.",
    "I found the system unnecessarily complex.",
    "I thought the system was easy to use.",
    "I think that I would need the support of a technical person to be able to use this system.",
    "I found the various functions in this system were well integrated.",
    "I thought there was too much inconsistency in this system.",
    "I would imagine that most people would learn to use this system very quickly.",
    "I found the system very cumbersome to use.",
    "I felt very confident using the system.",
    "I needed to learn a lot of things before I could get going with this system.",
]

_ADJECTIVE_BANDS = [
    (85.0, "Best Imaginable"),
    (73.0, "Excellent"),
    (52.0, "Good"),
    (39.0, "OK"),
    (25.0, "Poor"),
    (0.0, "Worst Imaginable"),
]


def compute_sus_score(responses: list[int]) -> float:
    """
    responses: 10 raw Likert answers (1-5) in item order. Odd items
    (0-indexed 0,2,4,6,8) score as (response - 1); even items score as
    (5 - response). Sum * 2.5 -> a 0-100 score.
    """
    if len(responses) != ITEM_COUNT:
        raise ValueError(f"Expected {ITEM_COUNT} responses, got {len(responses)}.")
    if any(response < 1 or response > 5 for response in responses):
        raise ValueError("Each response must be an integer from 1 to 5.")

    total = 0
    for index, response in enumerate(responses):
        total += (response - 1) if index % 2 == 0 else (5 - response)

    return round(total * 2.5, 2)


def adjective_rating(sus_score: float) -> str:
    for threshold, label in _ADJECTIVE_BANDS:
        if sus_score >= threshold:
            return label
    return _ADJECTIVE_BANDS[-1][1]


def aggregate_sus_scores(all_responses: list[list[int]]) -> dict:
    """all_responses: one 10-item response list per respondent."""
    if not all_responses:
        raise ValueError("Need at least one respondent's responses.")

    scores = [compute_sus_score(responses) for responses in all_responses]

    return {
        "respondent_count": len(scores),
        "individual_scores": scores,
        "mean_score": round(statistics.mean(scores), 2),
        "median_score": round(statistics.median(scores), 2),
        "stdev": round(statistics.stdev(scores), 2) if len(scores) > 1 else 0.0,
        "mean_adjective_rating": adjective_rating(statistics.mean(scores)),
    }


def write_report(report: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = REPORTS_DIR / f"sus_{timestamp}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report_path


def main() -> None:
    """CLI entry point: reads a JSON file of [[r1..r10], [r1..r10], ...] respondent responses."""
    parser = argparse.ArgumentParser(description="Score SUS questionnaire responses.")
    parser.add_argument("responses_file", type=str, help="Path to a JSON file: a list of 10-item response lists (1-5 each).")
    args = parser.parse_args()

    responses_path = Path(args.responses_file).resolve()
    try:
        all_responses = json.loads(responses_path.read_text(encoding="utf-8"))
        result = aggregate_sus_scores(all_responses)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Error: {error}")
        sys.exit(1)

    report_path = write_report(result)
    print(json.dumps(result, indent=2))
    print(f"Report written to: {report_path}")


if __name__ == "__main__":
    main()
