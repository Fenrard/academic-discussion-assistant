"""
CPU/memory resource usage on target hardware (CLAUDE.md's Evaluation
Metrics list: "Resource usage | CPU/memory on target hardware").

monitor_resources() is generic — it samples the current process's CPU%
and RSS memory on a background thread while any callable runs, so it
works for a pipeline call, a benchmark loop, or anything else. main()
wires it around the same real-pipeline benchmark evaluation/latency.py
uses, so `python evaluation/resources.py` gives one more axis on the
same run.
"""

import argparse
import json
import statistics
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import psutil

REPORTS_DIR = Path(__file__).resolve().parent / "reports"
BYTES_PER_MB = 1024 * 1024


class _ResourceSampler:
    """Background-thread sampler — collects (cpu_percent, rss_mb) pairs at a fixed interval."""

    def __init__(self, process: psutil.Process, sample_interval_seconds: float):
        self._process = process
        self._interval = sample_interval_seconds
        self._samples: list[tuple[float, float]] = []
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        self._process.cpu_percent(interval=None)  # prime the internal baseline, first call is always 0.0
        while not self._stop_event.is_set():
            cpu_percent = self._process.cpu_percent(interval=None)
            memory_mb = self._process.memory_info().rss / BYTES_PER_MB
            self._samples.append((cpu_percent, memory_mb))
            self._stop_event.wait(self._interval)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> list[tuple[float, float]]:
        self._stop_event.set()
        self._thread.join()
        return self._samples


def monitor_resources(func: Callable, *args, sample_interval_seconds: float = 0.2, **kwargs) -> dict:
    """
    Runs func(*args, **kwargs) on the current process while sampling
    CPU%/memory in the background. Returns {"result": ..., "usage": {...}}.
    """
    process = psutil.Process()
    sampler = _ResourceSampler(process, sample_interval_seconds)

    start_time = time.perf_counter()
    sampler.start()
    try:
        result = func(*args, **kwargs)
    finally:
        samples = sampler.stop()
    wall_seconds = round(time.perf_counter() - start_time, 4)

    cpu_values = [sample[0] for sample in samples] or [0.0]
    memory_values = [sample[1] for sample in samples] or [process.memory_info().rss / BYTES_PER_MB]

    usage = {
        "wall_seconds": wall_seconds,
        "sample_count": len(samples),
        "mean_cpu_percent": round(statistics.mean(cpu_values), 2),
        "peak_cpu_percent": round(max(cpu_values), 2),
        "mean_memory_mb": round(statistics.mean(memory_values), 2),
        "peak_memory_mb": round(max(memory_values), 2),
    }

    return {"result": result, "usage": usage}


def write_report(report: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = REPORTS_DIR / f"resources_{timestamp}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure CPU/memory usage of a full pipeline run on this machine.")
    parser.add_argument("audio_file", type=str, help="Path to a preprocessed 16kHz mono WAV file.")
    parser.add_argument("--denoise", action="store_true", help="Enable FFmpeg afftdn denoising.")
    parser.add_argument("--no-vad", action="store_true", help="Skip Silero VAD.")
    args = parser.parse_args()

    REPO_ROOT = Path(__file__).resolve().parent.parent
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    from backend.services.audio_service import LoadedModels, load_whisper_model, run_pipeline
    from backend.services.glossary_service import load_glossary

    audio_path = Path(args.audio_file).resolve()
    enable_vad = not args.no_vad

    try:
        # Load Silero once, up front, and pass it in — otherwise detect_speech()'s
        # `silero_vad_model or load_silero_vad()` fallback reloads the model from
        # scratch *inside* the monitored run, inflating exactly the CPU/memory
        # numbers this script exists to measure (same fix as evaluation/latency.py).
        silero_vad_model = None
        if enable_vad:
            from silero_vad import load_silero_vad

            silero_vad_model = load_silero_vad()

        models = LoadedModels(
            whisper_model=load_whisper_model(), glossary=load_glossary(), silero_vad_model=silero_vad_model
        )
        report = monitor_resources(
            run_pipeline, audio_path, models, enable_denoise=args.denoise, enable_vad=enable_vad
        )
    except (FileNotFoundError, ValueError, RuntimeError) as error:
        print(f"Error: {error}")
        sys.exit(1)

    usage_report = report["usage"]
    report_path = write_report(usage_report)
    print(json.dumps(usage_report, indent=2))
    print(f"Report written to: {report_path}")


if __name__ == "__main__":
    main()
