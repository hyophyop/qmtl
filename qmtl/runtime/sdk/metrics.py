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
    get_mapping_store,
    get_or_create_counter,
    get_or_create_gauge,
    get_or_create_histogram,
    increment_mapping_store,
    reset_metrics as reset_registered_metrics,
    set_test_value,
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


def _mapping(metric):
    return get_mapping_store(metric, dict)


def _set_scalar(metric, value):
    set_test_value(metric, value, factory=lambda: type(value)())


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

seamless_cache_hit_total = _counter(
    "seamless_cache_hit_total",
    "Total number of Seamless in-memory cache hits",
    ["node_id", "interval", "world_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

seamless_cache_miss_total = _counter(
    "seamless_cache_miss_total",
    "Total number of Seamless in-memory cache misses",
    ["node_id", "interval", "world_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

seamless_cache_resident_bytes = _gauge(
    "seamless_cache_resident_bytes",
    "Resident bytes held by Seamless in-memory cache",
    test_value_attr="_val",
    test_value_factory=lambda: 0,
    reset=lambda g: g.set(0),
)

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

as_of_advancement_events = _counter(
    "as_of_advancement_events",
    "Count of monotonic as_of promotions",
    ["node_id", "world_id"],
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
    ["node_id", "interval", "world_id", "flag_type"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

seamless_conformance_warning_total = _counter(
    "seamless_conformance_warning_total",
    "Total number of warnings recorded by the Seamless conformance pipeline",
    ["node_id", "interval", "world_id"],
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
    _mapping(orders_published_total)[w] = _mapping(orders_published_total).get(w, 0) + 1


def record_fill_ingested() -> None:
    w = _WORLD_ID
    fills_ingested_total.labels(world_id=w).inc()
    _mapping(fills_ingested_total)[w] = _mapping(fills_ingested_total).get(w, 0) + 1


def record_order_rejected(reason: str) -> None:
    w = _WORLD_ID
    orders_rejected_total.labels(world_id=w, reason=reason).inc()
    key = (w, reason)
    _mapping(orders_rejected_total)[key] = _mapping(orders_rejected_total).get(key, 0) + 1


def _update_pretrade_ratio() -> None:
    w = _WORLD_ID
    total = _mapping(pretrade_attempts_total).get(w, 0)
    rejected = sum(
        v for (wid, _), v in _mapping(pretrade_rejections_total).items() if wid == w
    )
    ratio = (rejected / total) if total else 0.0
    pretrade_rejection_ratio.labels(world_id=w).set(ratio)
    _mapping(pretrade_rejection_ratio)[w] = ratio


def record_pretrade_attempt() -> None:
    w = _WORLD_ID
    pretrade_attempts_total.labels(world_id=w).inc()
    _mapping(pretrade_attempts_total)[w] = _mapping(pretrade_attempts_total).get(w, 0) + 1
    _update_pretrade_ratio()


def record_pretrade_rejection(reason: str) -> None:
    w = _WORLD_ID
    pretrade_rejections_total.labels(world_id=w, reason=reason).inc()
    key = (w, reason)
    _mapping(pretrade_rejections_total)[key] = _mapping(pretrade_rejections_total).get(key, 0) + 1
    _update_pretrade_ratio()


def observe_cache_read(upstream_id: str, interval: int) -> None:
    """Increment read metrics for a given upstream/interval pair."""
    u = str(upstream_id)
    i = str(interval)
    cache_read_total.labels(upstream_id=u, interval=i).inc()
    _mapping(cache_read_total)[(u, i)] = _mapping(cache_read_total).get((u, i), 0) + 1
    ts = time.time()
    cache_last_read_timestamp.labels(upstream_id=u, interval=i).set(ts)
    _mapping(cache_last_read_timestamp)[(u, i)] = ts


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
    _set_scalar(backfill_jobs_in_progress, backfill_jobs_in_progress._value.get())


def observe_backfill_complete(node_id: str, interval: int, ts: int) -> None:
    n = str(node_id)
    i = str(interval)
    backfill_last_timestamp.labels(node_id=n, interval=i).set(ts)
    _mapping(backfill_last_timestamp)[(n, i)] = ts
    backfill_jobs_in_progress.dec()
    _set_scalar(backfill_jobs_in_progress, backfill_jobs_in_progress._value.get())


def observe_backfill_retry(node_id: str, interval: int) -> None:
    n = str(node_id)
    i = str(interval)
    backfill_retry_total.labels(node_id=n, interval=i).inc()
    _mapping(backfill_retry_total)[(n, i)] = _mapping(backfill_retry_total).get((n, i), 0) + 1


def observe_backfill_failure(node_id: str, interval: int) -> None:
    n = str(node_id)
    i = str(interval)
    backfill_failure_total.labels(node_id=n, interval=i).inc()
    _mapping(backfill_failure_total)[(n, i)] = _mapping(backfill_failure_total).get((n, i), 0) + 1
    backfill_jobs_in_progress.dec()
    _set_scalar(backfill_jobs_in_progress, backfill_jobs_in_progress._value.get())


def observe_backfill_completion_ratio(
    *, node_id: str, interval: str | int, lease_key: str, ratio: float
) -> None:
    n = str(node_id)
    i = str(interval)
    k = str(lease_key)
    backfill_completion_ratio.labels(node_id=n, interval=i, lease_key=k).set(ratio)
    _mapping(backfill_completion_ratio)[(n, i, k)] = ratio


def observe_sla_phase_duration(
    *, node_id: str, interval: str | int, phase: str, duration_ms: float
) -> None:
    n = str(node_id)
    i = str(interval)
    p = str(phase)
    seconds = duration_ms / 1000.0
    seamless_sla_deadline_seconds.labels(node_id=n, phase=p).observe(seconds)
    _mapping(seamless_sla_deadline_seconds).setdefault((n, p), []).append(seconds)

    world = _WORLD_ID
    if p == "storage_wait":
        seamless_storage_wait_ms.labels(node_id=n, interval=i, world_id=world).observe(duration_ms)
        _mapping(seamless_storage_wait_ms).setdefault((n, i, world), []).append(duration_ms)
    elif p == "backfill_wait":
        seamless_backfill_wait_ms.labels(node_id=n, interval=i, world_id=world).observe(duration_ms)
        _mapping(seamless_backfill_wait_ms).setdefault((n, i, world), []).append(duration_ms)
    elif p == "live_wait":
        seamless_live_wait_ms.labels(node_id=n, interval=i, world_id=world).observe(duration_ms)
        _mapping(seamless_live_wait_ms).setdefault((n, i, world), []).append(duration_ms)
    elif p == "total":
        seamless_total_ms.labels(node_id=n, interval=i, world_id=world).observe(duration_ms)
        _mapping(seamless_total_ms).setdefault((n, i, world), []).append(duration_ms)


def observe_conformance_report(
    *,
    node_id: str,
    interval: str | int | None,
    flags: Mapping[str, int],
    warnings: Sequence[str],
    world_id: str | None = None,
) -> None:
    """Record counts derived from a Seamless conformance report."""

    n = str(node_id)
    i = str(interval) if interval is not None else "unknown"
    w = str(world_id) if world_id is not None else _WORLD_ID

    for flag_type, count in flags.items():
        ft = str(flag_type)
        seamless_conformance_flag_total.labels(
            node_id=n, interval=i, world_id=w, flag_type=ft
        ).inc(count)
        key = (n, i, w, ft)
        _mapping(seamless_conformance_flag_total)[key] = (
            _mapping(seamless_conformance_flag_total).get(key, 0) + count
        )
    if warnings:
        seamless_conformance_warning_total.labels(
            node_id=n, interval=i, world_id=w
        ).inc(len(warnings))


def observe_nodecache_resident_bytes(node_id: str, resident: int) -> None:
    _observe_nodecache_resident_bytes(node_id, resident)


def observe_node_process(node_id: str, duration_ms: float) -> None:
    """Record execution duration and increment counter for ``node_id``."""
    n = str(node_id)
    node_processed_total.labels(node_id=n).inc()
    _mapping(node_processed_total)[n] = _mapping(node_processed_total).get(n, 0) + 1
    node_process_duration_ms.labels(node_id=n).observe(duration_ms)
    _mapping(node_process_duration_ms).setdefault(n, []).append(duration_ms)


def observe_node_process_failure(node_id: str) -> None:
    """Increment failure counter for ``node_id``."""
    n = str(node_id)
    node_process_failure_total.labels(node_id=n).inc()
    _mapping(node_process_failure_total)[n] = _mapping(node_process_failure_total).get(n, 0) + 1


def observe_warmup_ready(node_id: str, duration_ms: float) -> None:
    n = str(node_id)
    warmup_ready_nodes_total.labels(node_id=n).inc()
    warmup_ready_duration_ms.labels(node_id=n).observe(duration_ms)


def observe_gap_repair_latency(*, node_id: str, interval: str | int, duration_ms: float) -> None:
    n = str(node_id)
    i = str(interval)
    world = _WORLD_ID
    gap_repair_latency_ms.labels(node_id=n, interval=i, world_id=world).observe(duration_ms)
    _mapping(gap_repair_latency_ms).setdefault((n, i, world), []).append(duration_ms)


def observe_coverage_ratio(*, node_id: str, interval: str | int, ratio: float | None) -> None:
    if ratio is None:
        return
    n = str(node_id)
    i = str(interval)
    world = _WORLD_ID
    coverage_ratio.labels(node_id=n, interval=i, world_id=world).set(ratio)
    _mapping(coverage_ratio)[(n, i, world)] = ratio


def observe_seamless_cache_hit(
    *, node_id: str, interval: str | int, world_id: str | None
) -> None:
    n = str(node_id)
    i = str(interval)
    world = str(world_id) if world_id is not None else _WORLD_ID
    seamless_cache_hit_total.labels(node_id=n, interval=i, world_id=world).inc()
    _mapping(seamless_cache_hit_total)[(n, i, world)] = (
        _mapping(seamless_cache_hit_total).get((n, i, world), 0) + 1
    )


def observe_seamless_cache_miss(
    *, node_id: str, interval: str | int, world_id: str | None
) -> None:
    n = str(node_id)
    i = str(interval)
    world = str(world_id) if world_id is not None else _WORLD_ID
    seamless_cache_miss_total.labels(node_id=n, interval=i, world_id=world).inc()
    _mapping(seamless_cache_miss_total)[(n, i, world)] = (
        _mapping(seamless_cache_miss_total).get((n, i, world), 0) + 1
    )


def observe_seamless_cache_resident_bytes(resident_bytes: int) -> None:
    value = max(0, int(resident_bytes))
    seamless_cache_resident_bytes.set(value)
    _set_scalar(seamless_cache_resident_bytes, value)


def observe_rate_limiter_tokens(*, limiter: str, tokens: float, capacity: float) -> None:
    key = str(limiter)
    world = _WORLD_ID
    seamless_rl_tokens_available.labels(limiter=key, world_id=world).set(tokens)
    _mapping(seamless_rl_tokens_available)[(key, world)] = tokens


def observe_rate_limiter_drop(*, limiter: str) -> None:
    key = str(limiter)
    world = _WORLD_ID
    seamless_rl_dropped_total.labels(limiter=key, world_id=world).inc()
    _mapping(seamless_rl_dropped_total)[(key, world)] = (
        _mapping(seamless_rl_dropped_total).get((key, world), 0) + 1
    )


def observe_artifact_publish_latency(
    *, node_id: str, interval: str | int, duration_ms: float
) -> None:
    n = str(node_id)
    i = str(interval)
    world = _WORLD_ID
    artifact_publish_latency_ms.labels(node_id=n, interval=i, world_id=world).observe(duration_ms)
    _mapping(artifact_publish_latency_ms).setdefault((n, i, world), []).append(duration_ms)


def observe_artifact_bytes_written(
    *, node_id: str, interval: str | int, bytes_written: int
) -> None:
    n = str(node_id)
    i = str(interval)
    world = _WORLD_ID
    artifact_bytes_written.labels(node_id=n, interval=i, world_id=world).inc(bytes_written)
    _mapping(artifact_bytes_written)[(n, i, world)] = (
        _mapping(artifact_bytes_written).get((n, i, world), 0) + bytes_written
    )


def observe_fingerprint_collision(*, node_id: str, interval: str | int) -> None:
    n = str(node_id)
    i = str(interval)
    world = _WORLD_ID
    fingerprint_collisions.labels(node_id=n, interval=i, world_id=world).inc()
    _mapping(fingerprint_collisions)[(n, i, world)] = (
        _mapping(fingerprint_collisions).get((n, i, world), 0) + 1
    )


def observe_domain_hold(*, node_id: str, interval: str | int, reason: str) -> None:
    n = str(node_id)
    i = str(interval)
    r = str(reason)
    world = _WORLD_ID
    domain_gate_holds.labels(node_id=n, interval=i, world_id=world, reason=r).inc()
    _mapping(domain_gate_holds)[(n, i, world, r)] = (
        _mapping(domain_gate_holds).get((n, i, world, r), 0) + 1
    )


def observe_partial_fill(*, node_id: str, interval: str | int, reason: str) -> None:
    n = str(node_id)
    i = str(interval)
    r = str(reason)
    world = _WORLD_ID
    partial_fill_returns.labels(node_id=n, interval=i, world_id=world, reason=r).inc()
    _mapping(partial_fill_returns)[(n, i, world, r)] = (
        _mapping(partial_fill_returns).get((n, i, world, r), 0) + 1
    )


def observe_as_of_advancement_event(*, node_id: str, world_id: str | None) -> None:
    n = str(node_id)
    world = str(world_id) if world_id is not None else ""
    as_of_advancement_events.labels(node_id=n, world_id=world).inc()
    _mapping(as_of_advancement_events)[(n, world)] = (
        _mapping(as_of_advancement_events).get((n, world), 0) + 1
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
    _mapping(live_staleness_seconds)[(n, i, world)] = staleness_seconds


def start_metrics_server(port: int = 8000) -> None:
    """Expose metrics via an HTTP server."""
    start_http_server(port, registry=global_registry)


def collect_metrics() -> str:
    """Return metrics in text exposition format."""
    text: str = generate_latest(global_registry).decode()
    return text


def reset_metrics() -> None:
    """Reset metric values for tests."""
    global _WORLD_ID
    _WORLD_ID = "default"
    reset_registered_metrics(_REGISTERED_METRICS)
    _clear_nodecache_resident_bytes()
    _clear_cross_context_cache_hits()
