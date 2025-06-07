from __future__ import annotations

"""Prometheus metrics for DAG manager."""

from collections import deque
from typing import Deque

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

sentinel_gap_count = Gauge(
    "sentinel_gap_count",
    "Number of missing sentinel events detected",
    registry=registry,
)

orphan_queue_total = Gauge(
    "orphan_queue_total",
    "Number of orphan queues discovered during GC",
    registry=registry,
)


def observe_diff_duration(duration_ms: float) -> None:
    """Record a diff duration and update the p95 gauge."""
    _diff_samples.append(duration_ms)
    if not _diff_samples:
        return
    ordered = sorted(_diff_samples)
    idx = max(0, int(len(ordered) * 0.95) - 1)
    diff_duration_ms_p95.set(ordered[idx])


def start_metrics_server(port: int = 8000) -> None:
    """Start a background HTTP server to expose metrics."""
    start_http_server(port, registry=registry)


def collect_metrics() -> str:
    """Return metrics in text exposition format."""
    return generate_latest(registry).decode()


def reset_metrics() -> None:
    """Helper for tests to clear recorded samples and metric values."""
    _diff_samples.clear()
    diff_duration_ms_p95.set(0)
    queue_create_error_total._value.set(0)  # type: ignore[attr-defined]
    sentinel_gap_count.set(0)
    orphan_queue_total.set(0)
