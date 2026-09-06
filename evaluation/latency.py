"""
Per-stage latency breakdown + Real-Time Factor (CLAUDE.md build-priority
#11: evaluation/latency.py). Two halves:

  - Pure aggregation functions (aggregate_latencies, compute_rtf) that
    work on any list of {stage: seconds} dicts — these are what
    audio_service.run_pipeline() already returns as `stage_latencies`
    on every call, per-chunk or whole-file, so nothing new had to be
    instrumented for this to work.
  - A CLI benchmark (main()) that loads the real models once, runs the
    pipeline `--runs` times against a test file, and reports + plots
    the aggregate.

No argparse inside the importable functions — same convention as scripts/.
"""

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

REPORTS_DIR = Path(__file__).resolve().parent / "reports"
PLOTS_DIR = Path(__file__).resolve().parent / "plots"


def compute_rtf(processing_seconds: float, audio_duration_seconds: float) -> float:
    """Real-Time Factor: >1.0 means processing took longer than the audio itself."""
    if audio_duration_seconds <= 0:
        raise ValueError("audio_duration_seconds must be > 0.")
    return round(processing_seconds / audio_duration_seconds, 4)


def aggregate_latencies(runs: list[dict]) -> dict:
    """
    runs: [{"stage_latencies": {stage: seconds, ...}, "audio_duration_seconds": float}, ...]
    Returns per-stage mean/median/p95, the mean total per-run latency, and mean RTF.
    """
    if not runs:
        raise ValueError("Need at least one run to aggregate.")

    stage_names = sorted({stage for run in runs for stage in run["stage_latencies"]})
    per_stage = {}
    for stage in stage_names:
        values = [run["stage_latencies"].get(stage, 0.0) for run in runs]
        per_stage[stage] = {
            "mean": round(statistics.mean(values), 4),
            "median": round(statistics.median(values), 4),
            "p95": round(_percentile(values, 95), 4),
        }

    totals = [sum(run["stage_latencies"].values()) for run in runs]
    rtfs = [compute_rtf(total, run["audio_duration_seconds"]) for total, run in zip(totals, runs)]

    return {
        "run_count": len(runs),
        "per_stage": per_stage,
        "mean_total_seconds": round(statistics.mean(totals), 4),
        "mean_rtf": round(statistics.mean(rtfs), 4),
    }


def _percentile(values: list[float], percentile: float) -> float:
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    index = (percentile / 100) * (len(ordered) - 1)
    lower, upper = int(index), min(int(index) + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def write_report(report: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = REPORTS_DIR / f"latency_{timestamp}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report_path


def plot_stage_latencies(aggregate: dict, output_name: str = "stage_latencies.png") -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    stages = list(aggregate["per_stage"].keys())
    means = [aggregate["per_stage"][stage]["mean"] for stage in stages]

    figure, axis = plt.subplots(figsize=(8, 4.5))
    axis.bar(stages, means, color="#4C72B0")
    axis.set_ylabel("Mean latency (s)")
    axis.set_title(f"Per-stage latency (n={aggregate['run_count']} runs, RTF={aggregate['mean_rtf']})")
    axis.tick_params(axis="x", rotation=30)
    figure.tight_layout()

    output_path = PLOTS_DIR / output_name
    figure.savefig(output_path, dpi=150)
    plt.close(figure)
    return output_path


def benchmark_pipeline(audio_path: Path, runs: int = 3, enable_denoise: bool = False, enable_vad: bool = True) -> list[dict]:
    """Loads Whisper (and Silero VAD, if enabled) once and runs the real pipeline `runs` times against `audio_path`."""
    from backend.services.audio_service import LoadedModels, load_whisper_model, run_pipeline
    from backend.services.glossary_service import load_glossary

    # silero_vad_model matters here specifically: audio_service.detect_speech()
    # falls back to `silero_vad_model or load_silero_vad()` when it's None,
    # which is a reasonable best-effort default elsewhere but would mean this
    # benchmark's own "vad" stage timer measures a full model reload on every
    # single --runs iteration instead of real per-call VAD cost — silently
    # inflating the exact per-stage latency numbers this script exists to
    # produce for the manuscript. Loading it once here matches how the real
    # worker process does it (backend/worker/celery_app.py's _load_models()).
    silero_vad_model = None
    if enable_vad:
        from silero_vad import load_silero_vad

        silero_vad_model = load_silero_vad()

    models = LoadedModels(whisper_model=load_whisper_model(), glossary=load_glossary(), silero_vad_model=silero_vad_model)

    results = []
    for _ in range(runs):
        result = run_pipeline(audio_path, models, enable_denoise=enable_denoise, enable_vad=enable_vad)
        results.append({
            "stage_latencies": result["stage_latencies"],
            "audio_duration_seconds": result["audio_duration_seconds"],
        })
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark per-stage pipeline latency and RTF.")
    parser.add_argument("audio_file", type=str, help="Path to a preprocessed 16kHz mono WAV file.")
    parser.add_argument("--runs", type=int, default=3, help="Number of repetitions (default: 3).")
    parser.add_argument("--denoise", action="store_true", help="Enable RNNoise denoising.")
    parser.add_argument("--no-vad", action="store_true", help="Skip Silero VAD.")
    parser.add_argument("--no-plot", action="store_true", help="Skip writing the bar chart.")
    args = parser.parse_args()

    audio_path = Path(args.audio_file).resolve()

    try:
        runs = benchmark_pipeline(audio_path, runs=args.runs, enable_denoise=args.denoise, enable_vad=not args.no_vad)
        aggregate = aggregate_latencies(runs)
    except (FileNotFoundError, ValueError, RuntimeError) as error:
        print(f"Error: {error}")
        sys.exit(1)

    report_path = write_report(aggregate)
    print(json.dumps(aggregate, indent=2))
    print(f"Report written to: {report_path}")

    if not args.no_plot:
        plot_path = plot_stage_latencies(aggregate)
        print(f"Plot written to: {plot_path}")


if __name__ == "__main__":
    main()
