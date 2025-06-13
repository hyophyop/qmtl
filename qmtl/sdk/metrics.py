from __future__ import annotations

"""Prometheus metrics for the SDK cache layer."""

import time
from prometheus_client import (
    Counter,
    Gauge,
    generate_latest,
    start_http_server,
    REGISTRY as global_registry,
)

# Guard against re-registration when tests reload this module
if "cache_read_total" in global_registry._names_to_collectors:
    cache_read_total = global_registry._names_to_collectors["cache_read_total"]
else:
    cache_read_total = Counter(
        "cache_read_total",
        "Total number of cache reads grouped by upstream and interval",
        ["upstream_id", "interval"],
        registry=global_registry,
    )

if "cache_last_read_timestamp" in global_registry._names_to_collectors:
    cache_last_read_timestamp = global_registry._names_to_collectors["cache_last_read_timestamp"]
else:
    cache_last_read_timestamp = Gauge(
        "cache_last_read_timestamp",
        "Unix timestamp of the most recent cache read",
        ["upstream_id", "interval"],
        registry=global_registry,
    )

# Expose recorded values for tests
cache_read_total._vals = {}  # type: ignore[attr-defined]
cache_last_read_timestamp._vals = {}  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Backfill metrics
if "backfill_last_timestamp" in global_registry._names_to_collectors:
    backfill_last_timestamp = global_registry._names_to_collectors[
        "backfill_last_timestamp"
    ]
else:
    backfill_last_timestamp = Gauge(
        "backfill_last_timestamp",
        "Latest timestamp successfully backfilled",
        ["node_id", "interval"],
        registry=global_registry,
    )

if "backfill_jobs_in_progress" in global_registry._names_to_collectors:
    backfill_jobs_in_progress = global_registry._names_to_collectors[
        "backfill_jobs_in_progress"
    ]
else:
    backfill_jobs_in_progress = Gauge(
        "backfill_jobs_in_progress",
        "Number of active backfill jobs",
        registry=global_registry,
    )

if "backfill_failure_total" in global_registry._names_to_collectors:
    backfill_failure_total = global_registry._names_to_collectors[
        "backfill_failure_total"
    ]
else:
    backfill_failure_total = Counter(
        "backfill_failure_total",
        "Total number of backfill jobs that ultimately failed",
        ["node_id", "interval"],
        registry=global_registry,
    )

if "backfill_retry_total" in global_registry._names_to_collectors:
    backfill_retry_total = global_registry._names_to_collectors[
        "backfill_retry_total"
    ]
else:
    backfill_retry_total = Counter(
        "backfill_retry_total",
        "Total number of backfill retry attempts",
        ["node_id", "interval"],
        registry=global_registry,
    )

backfill_last_timestamp._vals = {}  # type: ignore[attr-defined]
backfill_jobs_in_progress._val = 0  # type: ignore[attr-defined]
backfill_failure_total._vals = {}  # type: ignore[attr-defined]
backfill_retry_total._vals = {}  # type: ignore[attr-defined]


def observe_cache_read(upstream_id: str, interval: int) -> None:
    """Increment read metrics for a given upstream/interval pair."""
    u = str(upstream_id)
    i = str(interval)
    cache_read_total.labels(upstream_id=u, interval=i).inc()
    cache_read_total._vals[(u, i)] = cache_read_total._vals.get((u, i), 0) + 1  # type: ignore[attr-defined]
    ts = time.time()
    cache_last_read_timestamp.labels(upstream_id=u, interval=i).set(ts)
    cache_last_read_timestamp._vals[(u, i)] = ts  # type: ignore[attr-defined]


def observe_backfill_start(node_id: str, interval: int) -> None:
    n = str(node_id)
    i = str(interval)
    backfill_jobs_in_progress.inc()
    backfill_jobs_in_progress._val = backfill_jobs_in_progress._value.get()  # type: ignore[attr-defined]


def observe_backfill_complete(node_id: str, interval: int, ts: int) -> None:
    n = str(node_id)
    i = str(interval)
    backfill_last_timestamp.labels(node_id=n, interval=i).set(ts)
    backfill_last_timestamp._vals[(n, i)] = ts  # type: ignore[attr-defined]
    backfill_jobs_in_progress.dec()
    backfill_jobs_in_progress._val = backfill_jobs_in_progress._value.get()  # type: ignore[attr-defined]


def observe_backfill_retry(node_id: str, interval: int) -> None:
    n = str(node_id)
    i = str(interval)
    backfill_retry_total.labels(node_id=n, interval=i).inc()
    backfill_retry_total._vals[(n, i)] = backfill_retry_total._vals.get((n, i), 0) + 1  # type: ignore[attr-defined]


def observe_backfill_failure(node_id: str, interval: int) -> None:
    n = str(node_id)
    i = str(interval)
    backfill_failure_total.labels(node_id=n, interval=i).inc()
    backfill_failure_total._vals[(n, i)] = backfill_failure_total._vals.get((n, i), 0) + 1  # type: ignore[attr-defined]
    backfill_jobs_in_progress.dec()
    backfill_jobs_in_progress._val = backfill_jobs_in_progress._value.get()  # type: ignore[attr-defined]


def start_metrics_server(port: int = 8000) -> None:
    """Expose metrics via an HTTP server."""
    start_http_server(port, registry=global_registry)


def collect_metrics() -> str:
    """Return metrics in text exposition format."""
    return generate_latest(global_registry).decode()


def reset_metrics() -> None:
    """Reset metric values for tests."""
    cache_read_total.clear()
    cache_read_total._vals = {}  # type: ignore[attr-defined]
    cache_last_read_timestamp.clear()
    cache_last_read_timestamp._vals = {}  # type: ignore[attr-defined]
    backfill_last_timestamp.clear()
    backfill_last_timestamp._vals = {}  # type: ignore[attr-defined]
    backfill_jobs_in_progress.set(0)
    backfill_jobs_in_progress._val = 0  # type: ignore[attr-defined]
    backfill_failure_total.clear()
    backfill_failure_total._vals = {}  # type: ignore[attr-defined]
    backfill_retry_total.clear()
    backfill_retry_total._vals = {}  # type: ignore[attr-defined]
