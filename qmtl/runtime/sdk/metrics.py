from __future__ import annotations

"""Prometheus metrics for the SDK cache layer."""

import time
from collections.abc import Mapping, Sequence

from prometheus_client import (
    generate_latest,
    start_http_server,
    REGISTRY as global_registry,
)
from qmtl.foundation.common.metrics_factory import (
    get_or_create_counter,
    get_or_create_gauge,
    get_or_create_histogram,
    reset_metrics as reset_registered_metrics,
)
from qmtl.foundation.common.metrics_shared import (
    get_cross_context_cache_hit_counter,
    get_nodecache_resident_bytes,
    observe_cross_context_cache_hit as _observe_cross_context_cache_hit,
    observe_nodecache_resident_bytes as _observe_nodecache_resident_bytes,
    clear_cross_context_cache_hits as _clear_cross_context_cache_hits,
    clear_nodecache_resident_bytes as _clear_nodecache_resident_bytes,
)

_WORLD_ID = "default"
_REGISTERED_METRICS: set[str] = set()


def _counter(
    name: str,
    documentation: str,
    labelnames: Sequence[str] | None = None,
    **kwargs,
):
    metric = get_or_create_counter(name, documentation, labelnames, **kwargs)
    _REGISTERED_METRICS.add(getattr(metric, "_name", name))
    return metric


def _gauge(
    name: str,
    documentation: str,
    labelnames: Sequence[str] | None = None,
    **kwargs,
):
    metric = get_or_create_gauge(name, documentation, labelnames, **kwargs)
    _REGISTERED_METRICS.add(getattr(metric, "_name", name))
    return metric


def _histogram(
    name: str,
    documentation: str,
    labelnames: Sequence[str] | None = None,
    **kwargs,
):
    metric = get_or_create_histogram(name, documentation, labelnames, **kwargs)
    _REGISTERED_METRICS.add(getattr(metric, "_name", name))
    return metric


def set_world_id(world_id: str) -> None:
    global _WORLD_ID
    _WORLD_ID = str(world_id)


# ---------------------------------------------------------------------------
# Cache metrics
# ---------------------------------------------------------------------------
cache_read_total = _counter(
    "cache_read_total",
    "Total number of cache reads grouped by upstream and interval",
    ["upstream_id", "interval"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

cache_last_read_timestamp = _gauge(
    "cache_last_read_timestamp",
    "Unix timestamp of the most recent cache read",
    ["upstream_id", "interval"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

cross_context_cache_hit_total = get_cross_context_cache_hit_counter()

# ---------------------------------------------------------------------------
# Backfill metrics
# ---------------------------------------------------------------------------
backfill_last_timestamp = _gauge(
    "backfill_last_timestamp",
    "Latest timestamp successfully backfilled",
    ["node_id", "interval"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

backfill_jobs_in_progress = _gauge(
    "backfill_jobs_in_progress",
    "Number of active backfill jobs",
    test_value_attr="_val",
    test_value_factory=lambda: 0,
    reset=lambda g: g.set(0),
)

backfill_failure_total = _counter(
    "backfill_failure_total",
    "Total number of backfill jobs that ultimately failed",
    ["node_id", "interval"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

backfill_retry_total = _counter(
    "backfill_retry_total",
    "Total number of backfill retry attempts",
    ["node_id", "interval"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

backfill_completion_ratio = _gauge(
    "backfill_completion_ratio",
    "Completion ratio reported by the distributed backfill coordinator",
    ["node_id", "interval", "lease_key"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

# ---------------------------------------------------------------------------
# SLA metrics
# ---------------------------------------------------------------------------
seamless_storage_wait_ms = _histogram(
    "seamless_storage_wait_ms",
    "Latency spent waiting on Seamless storage reads (milliseconds)",
    ["node_id", "interval", "world_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

seamless_backfill_wait_ms = _histogram(
    "seamless_backfill_wait_ms",
    "Latency spent waiting on Seamless backfill completion (milliseconds)",
    ["node_id", "interval", "world_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

seamless_live_wait_ms = _histogram(
    "seamless_live_wait_ms",
    "Latency spent waiting on Seamless live data feeds (milliseconds)",
    ["node_id", "interval", "world_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

seamless_total_ms = _histogram(
    "seamless_total_ms",
    "Total Seamless end-to-end request latency (milliseconds)",
    ["node_id", "interval", "world_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

seamless_sla_deadline_seconds = _histogram(
    "seamless_sla_deadline_seconds",
    "Observed SLA phase durations for Seamless data requests",
    ["node_id", "phase"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

coverage_ratio = _gauge(
    "coverage_ratio",
    "Ratio of bars delivered vs requested for Seamless responses",
    ["node_id", "interval", "world_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

gap_repair_latency_ms = _histogram(
    "gap_repair_latency_ms",
    "Latency to repair detected Seamless gaps (milliseconds)",
    ["node_id", "interval", "world_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

seamless_rl_tokens_available = _gauge(
    "seamless_rl_tokens_available",
    "Remaining Redis token bucket headroom for Seamless rate limiting",
    ["limiter", "world_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

seamless_rl_dropped_total = _counter(
    "seamless_rl_dropped_total",
    "Count of Seamless rate limited requests that exhausted token headroom",
    ["limiter", "world_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

artifact_publish_latency_ms = _histogram(
    "artifact_publish_latency_ms",
    "Latency from stabilization to artifact manifest publication (milliseconds)",
    ["node_id", "interval", "world_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

artifact_bytes_written = _counter(
    "artifact_bytes_written",
    "Total bytes written by Seamless artifact publications",
    ["node_id", "interval", "world_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

fingerprint_collisions = _counter(
    "fingerprint_collisions",
    "Count of duplicate dataset fingerprints observed during Seamless publication",
    ["node_id", "interval", "world_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

domain_gate_holds = _counter(
    "domain_gate_holds",
    "Number of Seamless responses downgraded to HOLD by domain gates",
    ["node_id", "interval", "world_id", "reason"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

partial_fill_returns = _counter(
    "partial_fill_returns",
    "Number of Seamless responses downgraded to PARTIAL_FILL",
    ["node_id", "interval", "world_id", "reason"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

live_staleness_seconds = _gauge(
    "live_staleness_seconds",
    "Observed live data staleness for Seamless responses (seconds)",
    ["node_id", "interval", "world_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

# ---------------------------------------------------------------------------
# Conformance metrics
# ---------------------------------------------------------------------------
seamless_conformance_flag_total = _counter(
    "seamless_conformance_flag_total",
    "Total number of conformance flags emitted by Seamless normalization",
    ["node_id", "flag_type"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

seamless_conformance_warning_total = _counter(
    "seamless_conformance_warning_total",
    "Total number of warnings recorded by the Seamless conformance pipeline",
    ["node_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

# ---------------------------------------------------------------------------
# History auto backfill metrics
# ---------------------------------------------------------------------------
history_auto_backfill_requests_total = _counter(
    "history_auto_backfill_requests_total",
    "Number of auto backfill ensure_range invocations",
    ["strategy", "node_id", "interval"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

history_auto_backfill_missing_ranges_total = _counter(
    "history_auto_backfill_missing_ranges_total",
    "Number of missing ranges detected by auto backfill",
    ["strategy", "node_id", "interval"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

history_auto_backfill_rows_total = _counter(
    "history_auto_backfill_rows_total",
    "Rows written by auto backfill strategies",
    ["strategy", "node_id", "interval"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

history_auto_backfill_duration_ms = _histogram(
    "history_auto_backfill_duration_ms",
    "Duration of auto backfill ensure_range calls in milliseconds",
    ["strategy"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

# Shared node cache metrics
nodecache_resident_bytes = get_nodecache_resident_bytes()

# ---------------------------------------------------------------------------
# Node execution metrics
# ---------------------------------------------------------------------------
node_processed_total = _counter(
    "node_processed_total",
    "Total number of node compute executions",
    ["node_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

node_process_duration_ms = _histogram(
    "node_process_duration_ms",
    "Duration of node compute execution in milliseconds",
    ["node_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

node_process_failure_total = _counter(
    "node_process_failure_total",
    "Total number of node compute failures",
    ["node_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

# ---------------------------------------------------------------------------
# Order lifecycle metrics (SDK-side)
# ---------------------------------------------------------------------------
orders_published_total = _counter(
    "orders_published_total",
    "Total orders published by SDK",
    ["world_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

fills_ingested_total = _counter(
    "fills_ingested_total",
    "Total fills ingested by SDK",
    ["world_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

orders_rejected_total = _counter(
    "orders_rejected_total",
    "Total pre-trade rejections at SDK",
    ["world_id", "reason"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

# ---------------------------------------------------------------------------
# Alpha performance metrics
# ---------------------------------------------------------------------------
alpha_sharpe = _gauge(
    "alpha_sharpe",
    "Alpha strategy Sharpe ratio",
    reset=lambda g: g.set(0.0),
    test_value_attr="_val",
    test_value_factory=lambda: 0.0,
)

alpha_max_drawdown = _gauge(
    "alpha_max_drawdown",
    "Alpha strategy maximum drawdown",
    reset=lambda g: g.set(0.0),
    test_value_attr="_val",
    test_value_factory=lambda: 0.0,
)

# ---------------------------------------------------------------------------
# Pre-trade rejection metrics (SDK-side)
# ---------------------------------------------------------------------------
pretrade_attempts_total = _counter(
    "pretrade_attempts_total",
    "Total number of pre-trade validation attempts",
    ["world_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

pretrade_rejections_total = _counter(
    "pretrade_rejections_total",
    "Total number of pre-trade rejections grouped by reason",
    ["world_id", "reason"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

pretrade_rejection_ratio = _gauge(
    "pretrade_rejection_ratio",
    "Ratio of rejected to attempted pre-trade validations",
    ["world_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

# ---------------------------------------------------------------------------
# Snapshot and warmup metrics
# ---------------------------------------------------------------------------
snapshot_write_duration_ms = _histogram(
    "snapshot_write_duration_ms",
    "Duration of snapshot writes in milliseconds",
)

warmup_ready_nodes_total = _counter(
    "warmup_ready_nodes_total",
    "Total number of nodes that completed warmup",
    ["node_id"],
)

warmup_ready_duration_ms = _histogram(
    "warmup_ready_duration_ms",
    "Duration from node creation to ready state in milliseconds",
    ["node_id"],
)

snapshot_bytes_total = _counter(
    "snapshot_bytes_total",
    "Total bytes written to snapshots",
)

snapshot_hydration_success_total = _counter(
    "snapshot_hydration_success_total",
    "Total number of successful snapshot hydrations",
)

snapshot_hydration_fallback_total = _counter(
    "snapshot_hydration_fallback_total",
    "Total number of hydration fallbacks due to snapshot mismatch",
)


def record_order_published() -> None:
    w = _WORLD_ID
    orders_published_total.labels(world_id=w).inc()
    orders_published_total._vals[w] = orders_published_total._vals.get(w, 0) + 1  # type: ignore[attr-defined]


def record_fill_ingested() -> None:
    w = _WORLD_ID
    fills_ingested_total.labels(world_id=w).inc()
    fills_ingested_total._vals[w] = fills_ingested_total._vals.get(w, 0) + 1  # type: ignore[attr-defined]


def record_order_rejected(reason: str) -> None:
    w = _WORLD_ID
    orders_rejected_total.labels(world_id=w, reason=reason).inc()
    key = (w, reason)
    orders_rejected_total._vals[key] = orders_rejected_total._vals.get(key, 0) + 1  # type: ignore[attr-defined]


def _update_pretrade_ratio() -> None:
    w = _WORLD_ID
    total = pretrade_attempts_total._vals.get(w, 0)  # type: ignore[attr-defined]
    rejected = sum(
        v for (wid, _), v in pretrade_rejections_total._vals.items() if wid == w
    )  # type: ignore[attr-defined]
    ratio = (rejected / total) if total else 0.0
    pretrade_rejection_ratio.labels(world_id=w).set(ratio)
    pretrade_rejection_ratio._vals[w] = ratio  # type: ignore[attr-defined]


def record_pretrade_attempt() -> None:
    w = _WORLD_ID
    pretrade_attempts_total.labels(world_id=w).inc()
    pretrade_attempts_total._vals[w] = pretrade_attempts_total._vals.get(w, 0) + 1  # type: ignore[attr-defined]
    _update_pretrade_ratio()


def record_pretrade_rejection(reason: str) -> None:
    w = _WORLD_ID
    pretrade_rejections_total.labels(world_id=w, reason=reason).inc()
    key = (w, reason)
    pretrade_rejections_total._vals[key] = pretrade_rejections_total._vals.get(key, 0) + 1  # type: ignore[attr-defined]
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


def observe_cross_context_cache_hit(
    node_id: str,
    world_id: str,
    execution_domain: str,
    *,
    as_of: str | None = None,
    partition: str | None = None,
) -> None:
    """Record a cache hit where the execution context mismatched."""

    _observe_cross_context_cache_hit(
        node_id,
        world_id,
        execution_domain,
        as_of=as_of,
        partition=partition,
    )


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


def observe_backfill_completion_ratio(
    *, node_id: str, interval: str | int, lease_key: str, ratio: float
) -> None:
    n = str(node_id)
    i = str(interval)
    k = str(lease_key)
    backfill_completion_ratio.labels(node_id=n, interval=i, lease_key=k).set(ratio)
    backfill_completion_ratio._vals[(n, i, k)] = ratio  # type: ignore[attr-defined]


def observe_sla_phase_duration(
    *, node_id: str, interval: str | int, phase: str, duration_ms: float
) -> None:
    n = str(node_id)
    i = str(interval)
    p = str(phase)
    seconds = duration_ms / 1000.0
    seamless_sla_deadline_seconds.labels(node_id=n, phase=p).observe(seconds)
    seamless_sla_deadline_seconds._vals.setdefault((n, p), []).append(seconds)  # type: ignore[attr-defined]

    world = _WORLD_ID
    if p == "storage_wait":
        seamless_storage_wait_ms.labels(node_id=n, interval=i, world_id=world).observe(duration_ms)
        seamless_storage_wait_ms._vals.setdefault((n, i, world), []).append(duration_ms)  # type: ignore[attr-defined]
    elif p == "backfill_wait":
        seamless_backfill_wait_ms.labels(node_id=n, interval=i, world_id=world).observe(duration_ms)
        seamless_backfill_wait_ms._vals.setdefault((n, i, world), []).append(duration_ms)  # type: ignore[attr-defined]
    elif p == "live_wait":
        seamless_live_wait_ms.labels(node_id=n, interval=i, world_id=world).observe(duration_ms)
        seamless_live_wait_ms._vals.setdefault((n, i, world), []).append(duration_ms)  # type: ignore[attr-defined]
    elif p == "total":
        seamless_total_ms.labels(node_id=n, interval=i, world_id=world).observe(duration_ms)
        seamless_total_ms._vals.setdefault((n, i, world), []).append(duration_ms)  # type: ignore[attr-defined]


def observe_conformance_report(
    *, node_id: str, flags: Mapping[str, int], warnings: Sequence[str]
) -> None:
    """Record counts derived from a Seamless conformance report."""

    n = str(node_id)
    for flag_type, count in flags.items():
        ft = str(flag_type)
        seamless_conformance_flag_total.labels(node_id=n, flag_type=ft).inc(count)
        key = (n, ft)
        seamless_conformance_flag_total._vals[key] = (  # type: ignore[attr-defined]
            seamless_conformance_flag_total._vals.get(key, 0) + count
        )
    if warnings:
        seamless_conformance_warning_total.labels(node_id=n).inc(len(warnings))
        seamless_conformance_warning_total._vals[n] = (  # type: ignore[attr-defined]
            seamless_conformance_warning_total._vals.get(n, 0) + len(warnings)
        )


def observe_nodecache_resident_bytes(node_id: str, resident: int) -> None:
    _observe_nodecache_resident_bytes(node_id, resident)


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


def observe_warmup_ready(node_id: str, duration_ms: float) -> None:
    n = str(node_id)
    warmup_ready_nodes_total.labels(node_id=n).inc()
    warmup_ready_duration_ms.labels(node_id=n).observe(duration_ms)


def observe_gap_repair_latency(*, node_id: str, interval: str | int, duration_ms: float) -> None:
    n = str(node_id)
    i = str(interval)
    world = _WORLD_ID
    gap_repair_latency_ms.labels(node_id=n, interval=i, world_id=world).observe(duration_ms)
    gap_repair_latency_ms._vals.setdefault((n, i, world), []).append(duration_ms)  # type: ignore[attr-defined]


def observe_coverage_ratio(*, node_id: str, interval: str | int, ratio: float | None) -> None:
    if ratio is None:
        return
    n = str(node_id)
    i = str(interval)
    world = _WORLD_ID
    coverage_ratio.labels(node_id=n, interval=i, world_id=world).set(ratio)
    coverage_ratio._vals[(n, i, world)] = ratio  # type: ignore[attr-defined]


def observe_rate_limiter_tokens(*, limiter: str, tokens: float, capacity: float) -> None:
    key = str(limiter)
    world = _WORLD_ID
    seamless_rl_tokens_available.labels(limiter=key, world_id=world).set(tokens)
    seamless_rl_tokens_available._vals[(key, world)] = tokens  # type: ignore[attr-defined]


def observe_rate_limiter_drop(*, limiter: str) -> None:
    key = str(limiter)
    world = _WORLD_ID
    seamless_rl_dropped_total.labels(limiter=key, world_id=world).inc()
    seamless_rl_dropped_total._vals[(key, world)] = (  # type: ignore[attr-defined]
        seamless_rl_dropped_total._vals.get((key, world), 0) + 1
    )


def observe_artifact_publish_latency(
    *, node_id: str, interval: str | int, duration_ms: float
) -> None:
    n = str(node_id)
    i = str(interval)
    world = _WORLD_ID
    artifact_publish_latency_ms.labels(node_id=n, interval=i, world_id=world).observe(duration_ms)
    artifact_publish_latency_ms._vals.setdefault((n, i, world), []).append(duration_ms)  # type: ignore[attr-defined]


def observe_artifact_bytes_written(
    *, node_id: str, interval: str | int, bytes_written: int
) -> None:
    n = str(node_id)
    i = str(interval)
    world = _WORLD_ID
    artifact_bytes_written.labels(node_id=n, interval=i, world_id=world).inc(bytes_written)
    artifact_bytes_written._vals[(n, i, world)] = (  # type: ignore[attr-defined]
        artifact_bytes_written._vals.get((n, i, world), 0) + bytes_written
    )


def observe_fingerprint_collision(*, node_id: str, interval: str | int) -> None:
    n = str(node_id)
    i = str(interval)
    world = _WORLD_ID
    fingerprint_collisions.labels(node_id=n, interval=i, world_id=world).inc()
    fingerprint_collisions._vals[(n, i, world)] = (  # type: ignore[attr-defined]
        fingerprint_collisions._vals.get((n, i, world), 0) + 1
    )


def observe_domain_hold(*, node_id: str, interval: str | int, reason: str) -> None:
    n = str(node_id)
    i = str(interval)
    r = str(reason)
    world = _WORLD_ID
    domain_gate_holds.labels(node_id=n, interval=i, world_id=world, reason=r).inc()
    domain_gate_holds._vals[(n, i, world, r)] = (  # type: ignore[attr-defined]
        domain_gate_holds._vals.get((n, i, world, r), 0) + 1
    )


def observe_partial_fill(*, node_id: str, interval: str | int, reason: str) -> None:
    n = str(node_id)
    i = str(interval)
    r = str(reason)
    world = _WORLD_ID
    partial_fill_returns.labels(node_id=n, interval=i, world_id=world, reason=r).inc()
    partial_fill_returns._vals[(n, i, world, r)] = (  # type: ignore[attr-defined]
        partial_fill_returns._vals.get((n, i, world, r), 0) + 1
    )


def observe_live_staleness(
    *, node_id: str, interval: str | int, staleness_seconds: float | None
) -> None:
    if staleness_seconds is None:
        return
    n = str(node_id)
    i = str(interval)
    world = _WORLD_ID
    live_staleness_seconds.labels(node_id=n, interval=i, world_id=world).set(staleness_seconds)
    live_staleness_seconds._vals[(n, i, world)] = staleness_seconds  # type: ignore[attr-defined]


def start_metrics_server(port: int = 8000) -> None:
    """Expose metrics via an HTTP server."""
    start_http_server(port, registry=global_registry)


def collect_metrics() -> str:
    """Return metrics in text exposition format."""
    return generate_latest(global_registry).decode()


def reset_metrics() -> None:
    """Reset metric values for tests."""
    global _WORLD_ID
    _WORLD_ID = "default"
    reset_registered_metrics(_REGISTERED_METRICS)
    _clear_nodecache_resident_bytes()
    _clear_cross_context_cache_hits()
