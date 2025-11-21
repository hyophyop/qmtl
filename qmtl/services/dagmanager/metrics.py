from __future__ import annotations

"""Prometheus metrics for DAG Manager."""

import argparse
import sys
import threading
import time
from collections import deque
from typing import Deque, Sequence

from prometheus_client import Gauge, Counter, generate_latest, start_http_server, REGISTRY as global_registry
from qmtl.foundation.common.metrics_factory import (
    get_or_create_counter,
    get_or_create_gauge,
    get_mapping_store,
    get_metric_value,
    increment_mapping_store,
    set_test_value,
)
from qmtl.foundation.common.metrics_shared import (
    get_nodecache_resident_bytes,
    observe_nodecache_resident_bytes as _observe_nodecache_resident_bytes,
    clear_nodecache_resident_bytes as _clear_nodecache_resident_bytes,
    get_cross_context_cache_hit_counter,
)
from qmtl.utils.i18n import _, set_language

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
# Diff request counters for throughput and failure-rate alerting
diff_requests_total = Counter(
    "diff_requests_total",
    "Total number of DAG diff requests processed",
    registry=global_registry,
)

diff_failures_total = Counter(
    "diff_failures_total",
    "Total number of failed DAG diff requests",
    registry=global_registry,
)

cross_context_cache_hit_total = get_cross_context_cache_hit_counter()

cross_context_cache_violation_total = get_or_create_counter(
    "cross_context_cache_violation_total",
    "Total number of cross-context cache violations detected during diff",
    ["node_id", "world_id", "execution_domain"],
    registry=global_registry,
    test_value_attr="_vals",
    test_value_factory=dict,
)
get_mapping_store(cross_context_cache_violation_total, dict)

sentinel_gap_count = Gauge(
    "sentinel_gap_count",
    "Number of missing sentinel events detected",
    registry=global_registry,
)
set_test_value(sentinel_gap_count, 0, factory=lambda: 0)

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
set_test_value(compute_nodes_total, 0, factory=lambda: 0)

queues_total = Gauge(
    "queues_total",
    "Total number of Queue nodes in Neo4j",
    registry=global_registry,
)
set_test_value(queues_total, 0, factory=lambda: 0)

# Per-topic Kafka consumer lag in seconds and configured alert thresholds.
queue_lag_seconds = get_or_create_gauge(
    "queue_lag_seconds",
    "Estimated consumer lag for each topic in seconds",
    ["topic"],
    registry=global_registry,
    test_value_attr="_vals",
    test_value_factory=dict,
)

queue_lag_threshold_seconds = get_or_create_gauge(
    "queue_lag_threshold_seconds",
    "Lag alert threshold configured for each topic",
    ["topic"],
    registry=global_registry,
    test_value_attr="_vals",
    test_value_factory=dict,
)

# Expose the active traffic weight per version. Guard against duplicate
# registration when this module is reloaded during tests.
dagmanager_active_version_weight = get_or_create_gauge(
    "dagmanager_active_version_weight",
    "Live traffic weight seen by Gateway for each model version",
    ["version"],
    registry=global_registry,
    test_value_attr="_vals",
    test_value_factory=dict,
)
get_mapping_store(dagmanager_active_version_weight, dict)

def set_active_version_weight(version: str, weight: float) -> None:
    dagmanager_active_version_weight.labels(version=version).set(weight)
    store = get_mapping_store(dagmanager_active_version_weight, dict)
    store[version] = weight


def observe_diff_duration(duration_ms: float) -> None:
    """Record a diff duration and update the p95 gauge."""
    _diff_samples.append(duration_ms)
    if not _diff_samples:
        return
    ordered = sorted(_diff_samples)
    idx = max(0, int(len(ordered) * 0.95) - 1)
    diff_duration_ms_p95.set(ordered[idx])
    set_test_value(diff_duration_ms_p95, ordered[idx], factory=float)


def observe_nodecache_resident_bytes(node_id: str, resident: int) -> None:
    _observe_nodecache_resident_bytes(node_id, resident)


def observe_queue_lag(topic: str, lag_seconds: float, threshold_seconds: float) -> None:
    """Record current lag and configured threshold for ``topic``."""
    queue_lag_seconds.labels(topic=topic).set(lag_seconds)
    queue_lag_seconds_store = get_mapping_store(queue_lag_seconds, dict)
    queue_lag_seconds_store[topic] = lag_seconds
    queue_lag_threshold_seconds.labels(topic=topic).set(threshold_seconds)
    threshold_store = get_mapping_store(queue_lag_threshold_seconds, dict)
    threshold_store[topic] = threshold_seconds


def start_metrics_server(port: int = 8000) -> None:
    """Start a background HTTP server to expose metrics."""
    start_http_server(port, registry=global_registry)

_stop_event = threading.Event()


def _run_forever(stop_event: threading.Event | None = None) -> None:
    """Block the main thread so the HTTP server stays alive."""
    stop_event = stop_event or _stop_event
    try:
        while not stop_event.wait(3600):
            pass
    except KeyboardInterrupt:  # pragma: no cover - manual stop
        pass


def _extract_lang(argv: Sequence[str]) -> tuple[list[str], str | None]:
    rest: list[str] = []
    lang: str | None = None

    i = 0
    tokens = list(argv)
    while i < len(tokens):
        token = tokens[i]
        if token.startswith("--lang="):
            lang = token.split("=", 1)[1]
            i += 1
            continue
        if token in {"--lang", "-L"}:
            if i + 1 < len(tokens):
                lang = tokens[i + 1]
                i += 2
                continue
            i += 1
            continue
        rest.append(token)
        i += 1
    return rest, lang


def main(argv: list[str] | None = None) -> None:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    original_is_none = argv is None
    raw_argv, lang = _extract_lang(raw_argv)
    if lang is not None:
        set_language(lang)
    elif original_is_none:
        set_language(None)

    parser = argparse.ArgumentParser(
        prog="qmtl service dagmanager metrics",
        description=_("Expose DAG Manager metrics"),
    )
    parser.add_argument(
        "--port", type=int, default=8000, help=_("Port to expose metrics on")
    )
    args = parser.parse_args(raw_argv)
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
    set_test_value(diff_duration_ms_p95, 0.0, factory=float)
    # Prometheus counters expose no public reset API; fall back to the backing
    # value object for test isolation.
    queue_create_error_total._value.set(0)  # type: ignore[attr-defined]
    set_test_value(queue_create_error_total, 0, factory=int)
    sentinel_gap_count.set(0)
    set_test_value(sentinel_gap_count, 0, factory=int)
    orphan_queue_total.set(0)
    set_test_value(orphan_queue_total, 0, factory=int)
    kafka_breaker_open_total.set(0)
    set_test_value(kafka_breaker_open_total, 0, factory=int)
    gc_last_run_timestamp.set(0)
    set_test_value(gc_last_run_timestamp, 0, factory=int)
    compute_nodes_total.set(0)
    set_test_value(compute_nodes_total, 0, factory=int)
    queues_total.set(0)
    set_test_value(queues_total, 0, factory=int)
    _clear_nodecache_resident_bytes()
    queue_lag_seconds.clear()
    get_mapping_store(queue_lag_seconds, dict).clear()
    queue_lag_threshold_seconds.clear()
    get_mapping_store(queue_lag_threshold_seconds, dict).clear()
    if hasattr(cross_context_cache_hit_total, "clear"):
        cross_context_cache_hit_total.clear()
    cross_context_cache_violation_total.clear()
    get_mapping_store(cross_context_cache_violation_total, dict).clear()
    if hasattr(dagmanager_active_version_weight, "clear"):
        dagmanager_active_version_weight.clear()
    get_mapping_store(dagmanager_active_version_weight, dict).clear()
    if hasattr(dagmanager_active_version_weight, "_metrics"):
        dagmanager_active_version_weight._metrics.clear()
