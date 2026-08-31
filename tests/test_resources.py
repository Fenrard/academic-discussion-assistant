import time

from evaluation.resources import monitor_resources


def _busy_wait(seconds: float) -> str:
    time.sleep(seconds)
    return "done"


def test_monitor_resources_returns_result_and_usage():
    report = monitor_resources(_busy_wait, 0.3, sample_interval_seconds=0.05)

    assert report["result"] == "done"
    usage = report["usage"]
    assert usage["wall_seconds"] >= 0.3
    assert usage["sample_count"] >= 1
    assert usage["peak_memory_mb"] > 0
    assert usage["mean_memory_mb"] > 0


def test_monitor_resources_propagates_exceptions():
    def _raises():
        raise RuntimeError("boom")

    try:
        monitor_resources(_raises, sample_interval_seconds=0.05)
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
