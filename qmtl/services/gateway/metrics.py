from __future__ import annotations

"""Prometheus metrics for Gateway."""

from collections import deque
from collections.abc import Sequence
from typing import Any, Deque, Mapping, cast
import time

from prometheus_client import (
    generate_latest,
    start_http_server,
    REGISTRY as global_registry,
)
from qmtl.foundation.common.metrics_factory import (
    get_or_create_counter,
    get_or_create_gauge,
    reset_metrics as reset_registered_metrics,
)

_e2e_samples: Deque[float] = deque(maxlen=100)
_worlds_samples: Deque[float] = deque(maxlen=100)
_sentinel_weight_updates: dict[str, float] = {}

_WORLD_ID = "default"
_REGISTERED_METRICS: set[str] = set()


def _vals(metric: object) -> dict[Any, Any]:
    metric_any = cast(Any, metric)
    vals = getattr(metric_any, "_vals", None)
    if vals is None:
        vals = {}
        metric_any._vals = vals
    return vals


def _value(metric: object) -> Any:
    return getattr(cast(Any, metric), "_value", {})


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


def set_world_id(world_id: str) -> None:
    global _WORLD_ID
    _WORLD_ID = str(world_id)


# ---------------------------------------------------------------------------
# Core Gateway health metrics
# ---------------------------------------------------------------------------
gateway_e2e_latency_p95 = _gauge(
    "gateway_e2e_latency_p95",
    "95th percentile end-to-end latency in milliseconds",
    test_value_attr="_val",
    test_value_factory=lambda: 0.0,
    reset=lambda g: g.set(0.0),
)

lost_requests_total = _counter(
    "lost_requests_total",
    "Total number of diff submissions lost due to queue errors",
    test_value_attr="_val",
    test_value_factory=lambda: 0,
)

commit_duplicate_total = _counter(
    "commit_duplicate_total",
    "Total number of duplicate commit-log records detected",
    test_value_attr="_val",
    test_value_factory=lambda: 0,
)

commit_invalid_total = _counter(
    "commit_invalid_total",
    "Total number of invalid commit-log records detected",
    test_value_attr="_val",
    test_value_factory=lambda: 0,
)

owner_reassign_total = _counter(
    "owner_reassign_total",
    "Total number of lease owner changes mid-bucket",
    test_value_attr="_val",
    test_value_factory=lambda: 0,
)

# DAG Manager breaker metrics
dagclient_breaker_state = _gauge(
    "dagclient_breaker_state",
    "DAG Manager circuit breaker state (1=open, 0=closed)",
    test_value_attr="_val",
    test_value_factory=lambda: 0,
    reset=lambda g: g.set(0),
)

dagclient_breaker_failures = _gauge(
    "dagclient_breaker_failures",
    "Consecutive failures recorded by the DAG Manager circuit breaker",
    test_value_attr="_val",
    test_value_factory=lambda: 0,
    reset=lambda g: g.set(0),
)

dagclient_breaker_open_total = _gauge(
    "dagclient_breaker_open_total",
    "Number of times the DAG Manager client breaker opened",
    test_value_attr="_val",
    test_value_factory=lambda: 0,
    reset=lambda g: g.set(0),
)

# WorldService proxy metrics
worlds_proxy_latency_p95 = _gauge(
    "worlds_proxy_latency_p95",
    "95th percentile latency of requests proxied to WorldService in milliseconds",
    test_value_attr="_val",
    test_value_factory=lambda: 0.0,
    reset=lambda g: g.set(0.0),
)

worlds_proxy_requests_total = _counter(
    "worlds_proxy_requests_total",
    "Total number of requests proxied to WorldService",
    test_value_attr="_val",
    test_value_factory=lambda: 0,
)

worlds_cache_hits_total = _counter(
    "worlds_cache_hits_total",
    "Total number of cache hits when proxying WorldService requests",
    test_value_attr="_val",
    test_value_factory=lambda: 0,
)

worlds_cache_hit_ratio = _gauge(
    "worlds_cache_hit_ratio",
    "Cache hit ratio for WorldService proxy requests",
    test_value_attr="_val",
    test_value_factory=lambda: 0.0,
    reset=lambda g: g.set(0),
)

worlds_stale_responses_total = _counter(
    "worlds_stale_responses_total",
    "Total number of stale cache responses served for WorldService requests",
    test_value_attr="_val",
    test_value_factory=lambda: 0,
)

worlds_compute_context_downgrade_total = _counter(
    "worlds_compute_context_downgrade_total",
    "Total number of decision compute contexts downgraded due to missing fields",
    ["reason"],
)

strategy_compute_context_downgrade_total = _counter(
    "strategy_compute_context_downgrade_total",
    "Total number of strategy submissions downgraded due to missing fields",
    ["reason"],
)

worlds_breaker_state = _gauge(
    "worlds_breaker_state",
    "WorldService circuit breaker state (1=open, 0=closed)",
    test_value_attr="_val",
    test_value_factory=lambda: 0,
    reset=lambda g: g.set(0),
)

worlds_breaker_failures = _gauge(
    "worlds_breaker_failures",
    "Consecutive failures recorded by the WorldService circuit breaker",
    test_value_attr="_val",
    test_value_factory=lambda: 0,
    reset=lambda g: g.set(0),
)

worlds_breaker_open_total = _gauge(
    "worlds_breaker_open_total",
    "Number of times the WorldService client breaker opened",
    test_value_attr="_val",
    test_value_factory=lambda: 0,
    reset=lambda g: g.set(0),
)

# ---------------------------------------------------------------------------
# Sentinel routing metrics
# ---------------------------------------------------------------------------
gateway_sentinel_traffic_ratio = _gauge(
    "gateway_sentinel_traffic_ratio",
    "Traffic ratio reported by each sentinel instance (0~1)",
    ["sentinel_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

sentinel_skew_seconds = _gauge(
    "sentinel_skew_seconds",
    "Seconds between sentinel weight update and observed traffic ratio",
    ["sentinel_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

# ---------------------------------------------------------------------------
# Rebalancing execution metrics
# ---------------------------------------------------------------------------
rebalance_batches_submitted_total = _counter(
    "rebalance_batches_submitted_total",
    "Total number of rebalancing order batches submitted",
    ["world_id", "scope"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

rebalance_last_batch_size = _gauge(
    "rebalance_last_batch_size",
    "Number of orders in the last submitted rebalancing batch",
    ["world_id", "scope"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

rebalance_reduce_only_ratio = _gauge(
    "rebalance_reduce_only_ratio",
    "Reduce-only ratio for the last submitted rebalancing batch",
    ["world_id", "scope"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

rebalance_plans_observed_total = _counter(
    "rebalance_plans_observed_total",
    "Total number of rebalancing plans observed via ControlBus",
    ["world_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

rebalance_plan_last_delta_count = _gauge(
    "rebalance_plan_last_delta_count",
    "Number of deltas included in the last observed rebalancing plan",
    ["world_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

rebalance_plan_execution_attempts_total = _counter(
    "rebalance_plan_execution_attempts_total",
    "Total number of automatic rebalancing execution attempts",
    ["world_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

rebalance_plan_execution_failures_total = _counter(
    "rebalance_plan_execution_failures_total",
    "Total number of automatic rebalancing execution failures",
    ["world_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

# ---------------------------------------------------------------------------
# Fills webhook metrics
# ---------------------------------------------------------------------------
fills_accepted_total = _counter(
    "fills_accepted_total",
    "Total number of accepted execution fill events",
    ["world_id", "strategy_id"],
)

fills_rejected_total = _counter(
    "fills_rejected_total",
    "Total number of rejected execution fill events",
    ["world_id", "strategy_id", "reason"],
)

# ---------------------------------------------------------------------------
# Degradation and ControlBus metrics
# ---------------------------------------------------------------------------
degrade_level = _gauge(
    "degrade_level",
    "Current degradation level",
    ["service"],
)

controlbus_lag_ms = _gauge(
    "controlbus_lag_ms",
    "Delay between event creation and processing in milliseconds",
    ["topic"],
)

event_relay_events_total = _counter(
    "event_relay_events_total",
    "Total number of ControlBus events relayed to clients",
    ["topic"],
)

event_relay_dropped_total = _counter(
    "event_relay_dropped_total",
    "Total number of ControlBus events dropped",
    ["topic"],
)

event_relay_skew_ms = _gauge(
    "event_relay_skew_ms",
    "Clock skew between event timestamp and relay time in milliseconds",
    ["topic"],
)

event_fanout_total = _counter(
    "event_fanout_total",
    "Total number of recipients for relayed ControlBus events",
    ["topic"],
)

ws_subscribers = _gauge(
    "ws_subscribers",
    "Active WebSocket subscribers per topic",
    ["topic"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

ws_dropped_subscribers_total = _counter(
    "ws_dropped_subscribers_total",
    "Total number of WebSocket subscribers dropped",
    test_value_attr="_val",
    test_value_factory=lambda: 0,
)

ws_connections_total = _counter(
    "ws_connections_total",
    "Total number of WebSocket connections accepted",
)

ws_disconnects_total = _counter(
    "ws_disconnects_total",
    "Total number of WebSocket connections closed by server",
)

ws_auth_failures_total = _counter(
    "ws_auth_failures_total",
    "Total number of WebSocket authentication failures",
)

ws_heartbeats_total = _counter(
    "ws_heartbeats_total",
    "Total number of heartbeats received from clients",
)

ws_acks_total = _counter(
    "ws_acks_total",
    "Total number of acknowledgements received from clients",
)

ws_refreshes_total = _counter(
    "ws_refreshes_total",
    "Total number of WebSocket token refresh requests",
)

ws_refresh_failures_total = _counter(
    "ws_refresh_failures_total",
    "Total number of failed WebSocket token refresh attempts",
)

# ---------------------------------------------------------------------------
# Gateway pre-trade metrics
# ---------------------------------------------------------------------------
pretrade_attempts_total = _counter(
    "gw_pretrade_attempts_total",
    "Total number of pre-trade validation attempts observed by Gateway",
    ["world_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

pretrade_rejections_total = _counter(
    "gw_pretrade_rejections_total",
    "Total pre-trade rejections grouped by reason at Gateway",
    ["world_id", "reason"],
    test_value_attr="_vals",
    test_value_factory=dict,
)

pretrade_rejection_ratio = _gauge(
    "gw_pretrade_rejection_ratio",
    "Ratio of rejected to attempted pre-trade validations seen by Gateway",
    ["world_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)


def record_pretrade_attempt() -> None:
    w = _WORLD_ID
    pretrade_attempts_total.labels(world_id=w).inc()
    attempts = _vals(pretrade_attempts_total)
    attempts[w] = attempts.get(w, 0) + 1
    _update_pretrade_ratio()


def record_pretrade_rejection(reason: str) -> None:
    w = _WORLD_ID
    pretrade_rejections_total.labels(world_id=w, reason=reason).inc()
    key = (w, reason)
    rejections = _vals(pretrade_rejections_total)
    rejections[key] = rejections.get(key, 0) + 1
    _update_pretrade_ratio()


def _update_pretrade_ratio() -> None:
    w = _WORLD_ID
    attempts = _vals(pretrade_attempts_total)
    total = attempts.get(w, 0)
    rejected = sum(v for (wid, _), v in _vals(pretrade_rejections_total).items() if wid == w)
    ratio = (rejected / total) if total else 0.0
    pretrade_rejection_ratio.labels(world_id=w).set(ratio)
    _vals(pretrade_rejection_ratio)[w] = ratio


def get_pretrade_stats() -> dict[str, object]:
    """Return a snapshot of pre-trade rejection counts and ratio for status."""

    w = _WORLD_ID
    return {
        "attempts": int(_vals(pretrade_attempts_total).get(w, 0)),
        "rejections": {
            reason: count
            for (wid, reason), count in _vals(pretrade_rejections_total).items()
            if wid == w
        },
        "ratio": float(_vals(pretrade_rejection_ratio).get(w, 0.0)),
    }


def record_sentinel_weight_update(sentinel_id: str) -> None:
    """Record the time when a sentinel weight update was received."""

    _sentinel_weight_updates[sentinel_id] = time.time()


def set_sentinel_traffic_ratio(sentinel_id: str, ratio: float) -> None:
    """Update the live traffic ratio for a sentinel version."""
    gateway_sentinel_traffic_ratio.labels(sentinel_id=sentinel_id).set(ratio)
    _vals(gateway_sentinel_traffic_ratio)[sentinel_id] = ratio
    if sentinel_id in _sentinel_weight_updates:
        skew = time.time() - _sentinel_weight_updates[sentinel_id]
        sentinel_skew_seconds.labels(sentinel_id=sentinel_id).set(skew)
        sentinel_label = cast(Any, sentinel_skew_seconds.labels(sentinel_id=sentinel_id))
        _vals(sentinel_skew_seconds)[sentinel_id] = sentinel_label._value.get()


def observe_gateway_latency(duration_ms: float) -> None:
    """Record a request latency and update the p95 gauge."""
    _e2e_samples.append(duration_ms)
    if not _e2e_samples:
        return
    ordered = sorted(_e2e_samples)
    idx = max(0, int(len(ordered) * 0.95) - 1)
    gateway_e2e_latency_p95.set(ordered[idx])
    cast(Any, gateway_e2e_latency_p95)._val = cast(Any, gateway_e2e_latency_p95)._value.get()


def observe_worlds_proxy_latency(duration_ms: float) -> None:
    """Record latency for WorldService proxy requests."""
    _worlds_samples.append(duration_ms)
    ordered = sorted(_worlds_samples)
    if ordered:
        idx = max(0, int(len(ordered) * 0.95) - 1)
        worlds_proxy_latency_p95.set(ordered[idx])
        cast(Any, worlds_proxy_latency_p95)._val = cast(Any, worlds_proxy_latency_p95)._value.get()
    worlds_proxy_requests_total.inc()
    cast(Any, worlds_proxy_requests_total)._val = cast(Any, worlds_proxy_requests_total)._value.get()
    _update_worlds_cache_ratio()


def record_worlds_cache_hit() -> None:
    """Record a cache hit for WorldService proxy."""
    worlds_cache_hits_total.inc()
    cast(Any, worlds_cache_hits_total)._val = cast(Any, worlds_cache_hits_total)._value.get()
    _update_worlds_cache_ratio()


def record_worlds_stale_response() -> None:
    """Record serving a stale WorldService cache entry."""
    worlds_stale_responses_total.inc()
    cast(Any, worlds_stale_responses_total)._val = cast(Any, worlds_stale_responses_total)._value.get()


def _update_worlds_cache_ratio() -> None:
    total = worlds_cache_hits_total._value.get() + worlds_proxy_requests_total._value.get()
    ratio = worlds_cache_hits_total._value.get() / total if total else 0
    worlds_cache_hit_ratio.set(ratio)
    cast(Any, worlds_cache_hit_ratio)._val = cast(Any, worlds_cache_hit_ratio)._value.get()


def record_controlbus_message(topic: str, timestamp_ms: float | None) -> None:
    """Record metrics for a ControlBus message being relayed."""

    event_relay_events_total.labels(topic=topic).inc()
    if timestamp_ms is not None:
        now_ms = time.time() * 1000
        controlbus_lag_ms.labels(topic=topic).set(max(0.0, now_ms - timestamp_ms))
        event_relay_skew_ms.labels(topic=topic).set(timestamp_ms - now_ms)


def record_event_dropped(topic: str) -> None:
    """Increment drop counter for ControlBus events."""
    event_relay_dropped_total.labels(topic=topic).inc()


def record_event_fanout(topic: str, recipients: int) -> None:
    """Record the number of recipients for a relayed event."""
    event_fanout_total.labels(topic=topic).inc(recipients)


def update_ws_subscribers(counts: dict[str, int]) -> None:
    """Update active WebSocket subscriber counts per topic."""
    ws_subscribers.clear()
    _vals(ws_subscribers).clear()
    for topic, count in counts.items():
        ws_subscribers.labels(topic=topic).set(count)
        _vals(ws_subscribers)[topic] = count


def record_ws_drop(count: int = 1) -> None:
    """Increment dropped subscriber counter."""
    ws_dropped_subscribers_total.inc(count)


def start_metrics_server(port: int = 8000) -> None:
    """Start an HTTP server to expose metrics."""
    start_http_server(port, registry=global_registry)


def collect_metrics() -> str:
    """Return metrics in text exposition format."""
    return generate_latest(global_registry).decode()


def record_rebalance_submission(
    world_id: str, scope: str, orders: Sequence[Mapping[str, Any]]
) -> None:
    """Record metrics for a submitted rebalancing batch."""

    rebalance_batches_submitted_total.labels(world_id=world_id, scope=scope).inc()
    total = len(orders)
    rebalance_last_batch_size.labels(world_id=world_id, scope=scope).set(total)
    reduce_only = sum(1 for order in orders if order.get("reduce_only"))
    ratio = float(reduce_only) / float(total) if total else 0.0
    rebalance_reduce_only_ratio.labels(world_id=world_id, scope=scope).set(ratio)


def record_rebalance_plan(world_id: str, delta_count: int) -> None:
    """Record metrics for an observed rebalancing plan."""

    rebalance_plans_observed_total.labels(world_id=world_id).inc()
    rebalance_plan_last_delta_count.labels(world_id=world_id).set(delta_count)


def record_rebalance_plan_execution(world_id: str, *, success: bool) -> None:
    """Record metrics for automatic rebalancing execution attempts."""

    rebalance_plan_execution_attempts_total.labels(world_id=world_id).inc()
    if not success:
        rebalance_plan_execution_failures_total.labels(world_id=world_id).inc()


def reset_metrics() -> None:
    """Reset all metric values for tests."""
    reset_registered_metrics(_REGISTERED_METRICS)
    _e2e_samples.clear()
    _worlds_samples.clear()
    _sentinel_weight_updates.clear()
    for metric in (
        rebalance_batches_submitted_total,
        rebalance_last_batch_size,
        rebalance_reduce_only_ratio,
        rebalance_plans_observed_total,
        rebalance_plan_last_delta_count,
        rebalance_plan_execution_attempts_total,
        rebalance_plan_execution_failures_total,
    ):
        if hasattr(metric, "_metrics"):
            cast(Any, metric)._metrics.clear()
        if hasattr(metric, "_vals"):
            _vals(metric).clear()
