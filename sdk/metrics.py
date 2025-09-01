from __future__ import annotations

"""Prometheus metrics for the SDK cache layer."""

import time
from typing import Mapping

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
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

# ---------------------------------------------------------------------------
if "nodecache_resident_bytes" in global_registry._names_to_collectors:
    nodecache_resident_bytes = global_registry._names_to_collectors[
        "nodecache_resident_bytes"
    ]
else:
    nodecache_resident_bytes = Gauge(
        "nodecache_resident_bytes",
        "Resident bytes held in node caches",
        ["node_id", "scope"],
        registry=global_registry,
    )

nodecache_resident_bytes._vals = {}  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
if "node_processed_total" in global_registry._names_to_collectors:
    node_processed_total = global_registry._names_to_collectors[
        "node_processed_total"
    ]
else:
    node_processed_total = Counter(
        "node_processed_total",
        "Total number of node compute executions",
        ["node_id"],
        registry=global_registry,
    )

if "node_process_duration_ms" in global_registry._names_to_collectors:
    node_process_duration_ms = global_registry._names_to_collectors[
        "node_process_duration_ms"
    ]
else:
    node_process_duration_ms = Histogram(
        "node_process_duration_ms",
        "Duration of node compute execution in milliseconds",
        ["node_id"],
        registry=global_registry,
    )

if "node_process_failure_total" in global_registry._names_to_collectors:
    node_process_failure_total = global_registry._names_to_collectors[
        "node_process_failure_total"
    ]
else:
    node_process_failure_total = Counter(
        "node_process_failure_total",
        "Total number of node compute failures",
        ["node_id"],
        registry=global_registry,
    )

node_processed_total._vals = {}  # type: ignore[attr-defined]
node_process_duration_ms._vals = {}  # type: ignore[attr-defined]
node_process_failure_total._vals = {}  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Alpha performance metrics
if "alpha_sharpe" in global_registry._names_to_collectors:
    alpha_sharpe = global_registry._names_to_collectors["alpha_sharpe"]
else:
    alpha_sharpe = Gauge(
        "alpha_sharpe",
        "Latest alpha Sharpe ratio",
        registry=global_registry,
    )

if "alpha_max_drawdown" in global_registry._names_to_collectors:
    alpha_max_drawdown = global_registry._names_to_collectors["alpha_max_drawdown"]
else:
    alpha_max_drawdown = Gauge(
        "alpha_max_drawdown",
        "Latest alpha max drawdown",
        registry=global_registry,
    )

alpha_sharpe._val = 0  # type: ignore[attr-defined]
alpha_max_drawdown._val = 0  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Pre-trade rejection metrics (SDK-side)
if "pretrade_attempts_total" in global_registry._names_to_collectors:
    pretrade_attempts_total = global_registry._names_to_collectors["pretrade_attempts_total"]
else:
    pretrade_attempts_total = Counter(
        "pretrade_attempts_total",
        "Total number of pre-trade validation attempts",
        registry=global_registry,
    )

if "pretrade_rejections_total" in global_registry._names_to_collectors:
    pretrade_rejections_total = global_registry._names_to_collectors["pretrade_rejections_total"]
else:
    pretrade_rejections_total = Counter(
        "pretrade_rejections_total",
        "Total number of pre-trade rejections grouped by reason",
        ["reason"],
        registry=global_registry,
    )

if "pretrade_rejection_ratio" in global_registry._names_to_collectors:
    pretrade_rejection_ratio = global_registry._names_to_collectors["pretrade_rejection_ratio"]
else:
    pretrade_rejection_ratio = Gauge(
        "pretrade_rejection_ratio",
        "Ratio of rejected to attempted pre-trade validations",
        registry=global_registry,
    )

# Expose values for tests
pretrade_attempts_total._val = 0  # type: ignore[attr-defined]
pretrade_rejections_total._vals = {}  # type: ignore[attr-defined]
pretrade_rejection_ratio._val = 0.0  # type: ignore[attr-defined]


def _update_pretrade_ratio() -> None:
    total = pretrade_attempts_total._value.get()
    rejected = sum(pretrade_rejections_total._vals.values())  # type: ignore[attr-defined]
    ratio = (rejected / total) if total else 0.0
    pretrade_rejection_ratio.set(ratio)
    pretrade_rejection_ratio._val = ratio  # type: ignore[attr-defined]


def record_pretrade_attempt() -> None:
    pretrade_attempts_total.inc()
    pretrade_attempts_total._val = pretrade_attempts_total._value.get()  # type: ignore[attr-defined]
    _update_pretrade_ratio()


def record_pretrade_rejection(reason: str) -> None:
    pretrade_rejections_total.labels(reason=reason).inc()
    pretrade_rejections_total._vals[reason] = pretrade_rejections_total._vals.get(reason, 0) + 1  # type: ignore[attr-defined]
    _update_pretrade_ratio()


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


def observe_nodecache_resident_bytes(node_id: str, resident: int) -> None:
    n = str(node_id)
    nodecache_resident_bytes.labels(node_id=n, scope="node").set(resident)
    nodecache_resident_bytes._vals[(n, "node")] = resident  # type: ignore[attr-defined]
    total = sum(
        v for (nid, sc), v in nodecache_resident_bytes._vals.items() if sc == "node"
    )
    nodecache_resident_bytes.labels(node_id="all", scope="total").set(total)
    nodecache_resident_bytes._vals[("all", "total")] = total  # type: ignore[attr-defined]


def observe_node_process(node_id: str, duration_ms: float) -> None:
    """Record execution duration and increment counter for ``node_id``."""
    n = str(node_id)
    node_processed_total.labels(node_id=n).inc()
    node_processed_total._vals[n] = node_processed_total._vals.get(n, 0) + 1  # type: ignore[attr-defined]
    node_process_duration_ms.labels(node_id=n).observe(duration_ms)
    node_process_duration_ms._vals.setdefault(n, []).append(duration_ms)  # type: ignore[attr-defined]


def observe_node_process_failure(node_id: str) -> None:
    """Increment failure counter for ``node_id``."""
    n = str(node_id)
    node_process_failure_total.labels(node_id=n).inc()
    node_process_failure_total._vals[n] = node_process_failure_total._vals.get(n, 0) + 1  # type: ignore[attr-defined]


def observe_alpha_performance(metrics: Mapping[str, float]) -> None:
    """Record alpha performance statistics."""
    sharpe = metrics.get("sharpe")
    if sharpe is not None:
        alpha_sharpe.set(sharpe)
        alpha_sharpe._val = sharpe  # type: ignore[attr-defined]
    mdd = metrics.get("max_drawdown")
    if mdd is not None:
        alpha_max_drawdown.set(mdd)
        alpha_max_drawdown._val = mdd  # type: ignore[attr-defined]


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
    nodecache_resident_bytes.clear()
    nodecache_resident_bytes._vals = {}  # type: ignore[attr-defined]
    node_processed_total.clear()
    node_processed_total._vals = {}  # type: ignore[attr-defined]
    node_process_duration_ms.clear()
    node_process_duration_ms._vals = {}  # type: ignore[attr-defined]
    node_process_failure_total.clear()
    node_process_failure_total._vals = {}  # type: ignore[attr-defined]
    alpha_sharpe.set(0)
    alpha_sharpe._val = 0  # type: ignore[attr-defined]
    alpha_max_drawdown.set(0)
    alpha_max_drawdown._val = 0  # type: ignore[attr-defined]
    pretrade_attempts_total._value.set(0)  # type: ignore[attr-defined]
    pretrade_attempts_total._val = 0  # type: ignore[attr-defined]
    pretrade_rejections_total.clear()
    pretrade_rejections_total._vals = {}  # type: ignore[attr-defined]
    pretrade_rejection_ratio.set(0)
    pretrade_rejection_ratio._val = 0.0  # type: ignore[attr-defined]
