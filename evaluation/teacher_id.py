"""
Teacher identification metrics (CLAUDE.md's Evaluation Metrics list:
"Teacher identification: precision/recall/F1 AND false-accept/
false-reject rate on enrolled vs unenrolled speakers" — plus overall
accuracy, the metric the thesis manuscript's Table 1 names separately
from precision/recall/F1; see docs/paper-vs-implementation.md).

Works on plain (predicted_is_teacher, actual_is_teacher) label pairs,
same shape backend.services.teacher_verification_service.verify_segment()
already returns per segment ({"is_teacher": bool, ...}) — a caller
builds the pairs from a manually-labeled evaluation set (ground truth
requires a human listening to segments, same as WER's reference
transcripts). No dependency on scikit-learn's metrics module even
though it's installed — the definitions are a handful of counts, not
worth a library call for.
"""

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPORTS_DIR = Path(__file__).resolve().parent / "reports"


@dataclass
class ConfusionCounts:
    true_positive: int = 0   # predicted teacher, actually teacher
    false_positive: int = 0  # predicted teacher, actually not (false accept)
    true_negative: int = 0   # predicted not-teacher, actually not
    false_negative: int = 0  # predicted not-teacher, actually teacher (false reject)


def _safe_divide(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def compute_confusion_counts(predictions: list[bool], actuals: list[bool]) -> ConfusionCounts:
    if len(predictions) != len(actuals):
        raise ValueError(f"predictions and actuals must be the same length, got {len(predictions)} and {len(actuals)}.")
    if not predictions:
        raise ValueError("Need at least one labeled segment to evaluate.")

    counts = ConfusionCounts()
    for predicted, actual in zip(predictions, actuals):
        if predicted and actual:
            counts.true_positive += 1
        elif predicted and not actual:
            counts.false_positive += 1
        elif not predicted and not actual:
            counts.true_negative += 1
        else:
            counts.false_negative += 1
    return counts


def compute_teacher_id_metrics(predictions: list[bool], actuals: list[bool]) -> dict:
    """
    "Enrolled" (actual=True) is the teacher's own voice; "unenrolled"
    (actual=False) is anyone else. False-accept rate (FAR) = an
    unenrolled speaker wrongly accepted as the teacher. False-reject
    rate (FRR) = the enrolled teacher wrongly rejected.
    """
    counts = compute_confusion_counts(predictions, actuals)

    precision = _safe_divide(counts.true_positive, counts.true_positive + counts.false_positive)
    recall = _safe_divide(counts.true_positive, counts.true_positive + counts.false_negative)
    f1 = _safe_divide(2 * precision * recall, precision + recall)
    # Correct classifications (teacher and non-teacher alike) over all segments — the
    # paper's Table 1 lists this as its own metric, distinct from precision/recall/F1,
    # so it's reported here rather than left for the caller to derive from `counts`.
    accuracy = _safe_divide(counts.true_positive + counts.true_negative, len(predictions))

    # FAR is measured against the unenrolled population, FRR against the enrolled population.
    unenrolled_count = counts.false_positive + counts.true_negative
    enrolled_count = counts.true_positive + counts.false_negative
    far = _safe_divide(counts.false_positive, unenrolled_count)
    frr = _safe_divide(counts.false_negative, enrolled_count)

    return {
        "counts": vars(counts),
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_accept_rate": far,
        "false_reject_rate": frr,
        "segment_count": len(predictions),
    }


def write_report(report: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = REPORTS_DIR / f"teacher_id_{timestamp}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report_path


def main() -> None:
    """
    CLI entry point: reads a JSON file of [{"predicted": bool, "actual": bool}, ...]
    labeled segments (built by hand-labeling a session's transcript_segments
    against who was actually speaking) and reports the metrics above.
    """
    parser = argparse.ArgumentParser(description="Compute teacher-ID precision/recall/F1/FAR/FRR from labeled segments.")
    parser.add_argument("labels_file", type=str, help="Path to a JSON file: [{\"predicted\": bool, \"actual\": bool}, ...]")
    args = parser.parse_args()

    labels_path = Path(args.labels_file).resolve()
    try:
        labels = json.loads(labels_path.read_text(encoding="utf-8"))
        predictions = [entry["predicted"] for entry in labels]
        actuals = [entry["actual"] for entry in labels]
        result = compute_teacher_id_metrics(predictions, actuals)
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as error:
        print(f"Error: {error}")
        sys.exit(1)

    report_path = write_report(result)
    print(json.dumps(result, indent=2))
    print(f"Report written to: {report_path}")


if __name__ == "__main__":
    main()
