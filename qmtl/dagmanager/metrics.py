from __future__ import annotations

"""Prometheus metrics for DAG Manager."""

from collections import deque
from typing import Deque, List
import time
import argparse

from prometheus_client import Gauge, Counter, generate_latest, start_http_server, REGISTRY as global_registry
from qmtl.common.metrics_shared import (
    get_nodecache_resident_bytes,
    observe_nodecache_resident_bytes as _observe_nodecache_resident_bytes,
    clear_nodecache_resident_bytes as _clear_nodecache_resident_bytes,
)

# Metrics defined in documentation
# 95th percentile diff duration in milliseconds
_diff_samples: Deque[float] = deque(maxlen=100)

diff_duration_ms_p95 = Gauge(
    "diff_duration_ms_p95",
    "95th percentile duration of diff processing in milliseconds",
    registry=global_registry,
)

queue_create_error_total = Counter(
    "queue_create_error_total",
    "Total number of queue creation failures",
    registry=global_registry,
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
    registry=global_registry,
)
sentinel_gap_count._val = 0  # type: ignore[attr-defined]

nodecache_resident_bytes = get_nodecache_resident_bytes()

orphan_queue_total = Gauge(
    "orphan_queue_total",
    "Number of orphan queues discovered during GC",
    registry=global_registry,
)

kafka_breaker_open_total = Gauge(
    "kafka_breaker_open_total",
    "Number of times the Kafka admin circuit breaker opened",
    registry=global_registry,
)

gc_last_run_timestamp = Gauge(
    "gc_last_run_timestamp",
    "Timestamp of the last successful garbage collection",
    registry=global_registry,
)

# Current graph size
compute_nodes_total = Gauge(
    "compute_nodes_total",
    "Total number of ComputeNode nodes in Neo4j",
    registry=global_registry,
)
compute_nodes_total._val = 0  # type: ignore[attr-defined]

queues_total = Gauge(
    "queues_total",
    "Total number of Queue nodes in Neo4j",
    registry=global_registry,
)
queues_total._val = 0  # type: ignore[attr-defined]

# Per-topic Kafka consumer lag in seconds and configured alert thresholds.
queue_lag_seconds = Gauge(
    "queue_lag_seconds",
    "Estimated consumer lag for each topic in seconds",
    ["topic"],
    registry=global_registry,
)
queue_lag_seconds._vals = {}  # type: ignore[attr-defined]

queue_lag_threshold_seconds = Gauge(
    "queue_lag_threshold_seconds",
    "Lag alert threshold configured for each topic",
    ["topic"],
    registry=global_registry,
)
queue_lag_threshold_seconds._vals = {}  # type: ignore[attr-defined]

# Expose the active traffic weight per version. Guard against duplicate
# registration when this module is reloaded during tests.
if "dagmanager_active_version_weight" in global_registry._names_to_collectors:
    dagmanager_active_version_weight = global_registry._names_to_collectors[
        "dagmanager_active_version_weight"
    ]
else:
    dagmanager_active_version_weight = Gauge(
        "dagmanager_active_version_weight",
        "Live traffic weight seen by Gateway for each model version",
        ["version"],
        registry=global_registry,
    )

dagmanager_active_version_weight._vals = {}  # type: ignore[attr-defined]

def set_active_version_weight(version: str, weight: float) -> None:
    dagmanager_active_version_weight.labels(version=version).set(weight)
    dagmanager_active_version_weight._vals[version] = weight  # type: ignore[attr-defined]


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


def observe_nodecache_resident_bytes(node_id: str, resident: int) -> None:
    _observe_nodecache_resident_bytes(node_id, resident)


def observe_queue_lag(topic: str, lag_seconds: float, threshold_seconds: float) -> None:
    """Record current lag and configured threshold for ``topic``."""
    queue_lag_seconds.labels(topic=topic).set(lag_seconds)
    queue_lag_seconds._vals[topic] = lag_seconds  # type: ignore[attr-defined]
    queue_lag_threshold_seconds.labels(topic=topic).set(threshold_seconds)
    queue_lag_threshold_seconds._vals[topic] = threshold_seconds  # type: ignore[attr-defined]


def start_metrics_server(port: int = 8000) -> None:
    """Start a background HTTP server to expose metrics."""
    start_http_server(port, registry=global_registry)


def _run_forever() -> None:
    """Block the main thread so the HTTP server stays alive."""
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:  # pragma: no cover - manual stop
        pass


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="qmtl dagmanager-metrics",
        description="Expose DAG Manager metrics",
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Port to expose metrics on"
    )
    args = parser.parse_args(argv)
    start_metrics_server(args.port)
    _run_forever()


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()


def collect_metrics() -> str:
    """Return metrics in text exposition format."""
    return generate_latest(global_registry).decode()


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
    kafka_breaker_open_total.set(0)
    kafka_breaker_open_total._val = 0  # type: ignore[attr-defined]
    gc_last_run_timestamp.set(0)
    gc_last_run_timestamp._val = 0  # type: ignore[attr-defined]
    compute_nodes_total.set(0)
    compute_nodes_total._val = 0  # type: ignore[attr-defined]
    queues_total.set(0)
    queues_total._val = 0  # type: ignore[attr-defined]
    _clear_nodecache_resident_bytes()
    queue_lag_seconds.clear()
    queue_lag_seconds._vals = {}  # type: ignore[attr-defined]
    queue_lag_threshold_seconds.clear()
    queue_lag_threshold_seconds._vals = {}  # type: ignore[attr-defined]
    if hasattr(dagmanager_active_version_weight, "clear"):
        dagmanager_active_version_weight.clear()
    dagmanager_active_version_weight._vals = {}  # type: ignore[attr-defined]
    if hasattr(dagmanager_active_version_weight, "_metrics"):
        dagmanager_active_version_weight._metrics.clear()
