from __future__ import annotations

"""Prometheus metrics for DAG manager."""

from collections import deque
from typing import Deque
import time

from prometheus_client import Gauge, Counter, CollectorRegistry, generate_latest, start_http_server

registry = CollectorRegistry()

# Metrics defined in documentation
# 95th percentile diff duration in milliseconds
_diff_samples: Deque[float] = deque(maxlen=100)

diff_duration_ms_p95 = Gauge(
    "diff_duration_ms_p95",
    "95th percentile duration of diff processing in milliseconds",
    registry=registry,
)

queue_create_error_total = Counter(
    "queue_create_error_total",
    "Total number of queue creation failures",
    registry=registry,
)
# expose value proxy for tests
class _ValueProxy:
    def __init__(self, mv) -> None:
        self._mv = mv

    def set(self, val: float) -> None:
        self._mv.set(val)

    def inc(self, amount: float = 1) -> None:  # pragma: no cover - passthrough
        self._mv.inc(amount)

    def get_exemplar(self):  # pragma: no cover - passthrough
        return self._mv.get_exemplar()

    def get(self) -> float:
        return self._mv.get()

    def __eq__(self, other: object) -> bool:  # pragma: no cover - simple
        try:
            return self._mv.get() == other
        except Exception:
            return False

queue_create_error_total._raw_value = queue_create_error_total._value  # type: ignore[attr-defined]
queue_create_error_total._value = _ValueProxy(queue_create_error_total._raw_value)  # type: ignore[attr-defined]

sentinel_gap_count = Gauge(
    "sentinel_gap_count",
    "Number of missing sentinel events detected",
    registry=registry,
)
sentinel_gap_count._val = 0  # type: ignore[attr-defined]

orphan_queue_total = Gauge(
    "orphan_queue_total",
    "Number of orphan queues discovered during GC",
    registry=registry,
)

# Expose the active traffic weight per version. Guard against duplicate
# registration when this module is reloaded during tests.
if "dagmgr_active_version_weight" in registry._names_to_collectors:
    dagmgr_active_version_weight = registry._names_to_collectors[
        "dagmgr_active_version_weight"
    ]
else:
    dagmgr_active_version_weight = Gauge(
        "dagmgr_active_version_weight",
        "Traffic weight applied to a strategy version",
        ["version"],
        registry=registry,
    )
)
dagmgr_active_version_weight._vals = {}  # type: ignore[attr-defined]

active_version_weight = Gauge(
    "dagmgr_active_version_weight",
    "Traffic weight for active DAG version",
    ["version"],
    registry=registry,
)
active_version_weight = Gauge(
    "dagmgr_active_version_weight",
    "Traffic weight for active DAG version",
    ["version"],
    registry=registry,
)

def set_active_version_weight(version: str, weight: float) -> None:
    """Record the weight currently applied to a version."""
    dagmgr_active_version_weight.labels(version=version).set(weight)
    dagmgr_active_version_weight._vals[version] = weight  # type: ignore[attr-defined]
    active_version_weight.labels(version=version).set(weight)


def observe_diff_duration(duration_ms: float) -> None:
    """Record a diff duration and update the p95 gauge."""
    _diff_samples.append(duration_ms)
    if not _diff_samples:
        return
    ordered = sorted(_diff_samples)
    idx = max(0, int(len(ordered) * 0.95) - 1)
    diff_duration_ms_p95.set(ordered[idx])
    # expose raw value for tests
    diff_duration_ms_p95._val = diff_duration_ms_p95._value.get()  # type: ignore[attr-defined]


def start_metrics_server(port: int = 8000) -> None:
    """Start a background HTTP server to expose metrics."""
    start_http_server(port, registry=registry)


def _run_forever() -> None:
    """Block the main thread so the HTTP server stays alive."""
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:  # pragma: no cover - manual stop
        pass


def main() -> None:  # pragma: no cover - thin wrapper
    start_metrics_server()
    _run_forever()


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()


def collect_metrics() -> str:
    """Return metrics in text exposition format."""
    return generate_latest(registry).decode()


def reset_metrics() -> None:
    """Helper for tests to clear recorded samples and metric values."""
    _diff_samples.clear()
    diff_duration_ms_p95.set(0)
    diff_duration_ms_p95._val = 0  # type: ignore[attr-defined]
    queue_create_error_total._value.set(0)  # type: ignore[attr-defined]
    queue_create_error_total._val = 0  # type: ignore[attr-defined]
    sentinel_gap_count.set(0)
    sentinel_gap_count._val = 0  # type: ignore[attr-defined]
    orphan_queue_total.set(0)
    orphan_queue_total._val = 0  # type: ignore[attr-defined]
    dagmgr_active_version_weight.clear()
    dagmgr_active_version_weight._vals = {}  # type: ignore[attr-defined]
