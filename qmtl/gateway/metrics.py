from __future__ import annotations

"""Prometheus metrics for Gateway."""

from collections import deque
from collections.abc import Sequence
from typing import Deque
import time

from prometheus_client import (
    generate_latest,
    start_http_server,
    REGISTRY as global_registry,
)
from qmtl.common.metrics_factory import (
    get_or_create_counter,
    get_or_create_gauge,
    reset_metrics as reset_registered_metrics,
)

_e2e_samples: Deque[float] = deque(maxlen=100)
_worlds_samples: Deque[float] = deque(maxlen=100)
_sentinel_weight_updates: dict[str, float] = {}

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
    pretrade_attempts_total._vals[w] = pretrade_attempts_total._vals.get(w, 0) + 1  # type: ignore[attr-defined]
    _update_pretrade_ratio()


def record_pretrade_rejection(reason: str) -> None:
    w = _WORLD_ID
    pretrade_rejections_total.labels(world_id=w, reason=reason).inc()
    key = (w, reason)
    pretrade_rejections_total._vals[key] = pretrade_rejections_total._vals.get(key, 0) + 1  # type: ignore[attr-defined]
    _update_pretrade_ratio()


def _update_pretrade_ratio() -> None:
    w = _WORLD_ID
    total = pretrade_attempts_total._vals.get(w, 0)  # type: ignore[attr-defined]
    rejected = sum(
        v for (wid, _), v in pretrade_rejections_total._vals.items() if wid == w
    )  # type: ignore[attr-defined]
    ratio = (rejected / total) if total else 0.0
    pretrade_rejection_ratio.labels(world_id=w).set(ratio)
    pretrade_rejection_ratio._vals[w] = ratio  # type: ignore[attr-defined]


def get_pretrade_stats() -> dict[str, object]:
    """Return a snapshot of pre-trade rejection counts and ratio for status."""

    w = _WORLD_ID
    return {
        "attempts": int(pretrade_attempts_total._vals.get(w, 0)),  # type: ignore[attr-defined]
        "rejections": {
            reason: count
            for (wid, reason), count in pretrade_rejections_total._vals.items()  # type: ignore[attr-defined]
            if wid == w
        },
        "ratio": float(pretrade_rejection_ratio._vals.get(w, 0.0)),  # type: ignore[attr-defined]
    }


def record_sentinel_weight_update(sentinel_id: str) -> None:
    """Record the time when a sentinel weight update was received."""

    _sentinel_weight_updates[sentinel_id] = time.time()


def set_sentinel_traffic_ratio(sentinel_id: str, ratio: float) -> None:
    """Update the live traffic ratio for a sentinel version."""
    gateway_sentinel_traffic_ratio.labels(sentinel_id=sentinel_id).set(ratio)
    gateway_sentinel_traffic_ratio._vals[sentinel_id] = ratio  # type: ignore[attr-defined]
    if sentinel_id in _sentinel_weight_updates:
        skew = time.time() - _sentinel_weight_updates[sentinel_id]
        sentinel_skew_seconds.labels(sentinel_id=sentinel_id).set(skew)
        sentinel_skew_seconds._vals[sentinel_id] = sentinel_skew_seconds.labels(  # type: ignore[attr-defined]
            sentinel_id=sentinel_id
        )._value.get()


def observe_gateway_latency(duration_ms: float) -> None:
    """Record a request latency and update the p95 gauge."""
    _e2e_samples.append(duration_ms)
    if not _e2e_samples:
        return
    ordered = sorted(_e2e_samples)
    idx = max(0, int(len(ordered) * 0.95) - 1)
    gateway_e2e_latency_p95.set(ordered[idx])
    gateway_e2e_latency_p95._val = gateway_e2e_latency_p95._value.get()  # type: ignore[attr-defined]


def observe_worlds_proxy_latency(duration_ms: float) -> None:
    """Record latency for WorldService proxy requests."""
    _worlds_samples.append(duration_ms)
    ordered = sorted(_worlds_samples)
    if ordered:
        idx = max(0, int(len(ordered) * 0.95) - 1)
        worlds_proxy_latency_p95.set(ordered[idx])
        worlds_proxy_latency_p95._val = worlds_proxy_latency_p95._value.get()  # type: ignore[attr-defined]
    worlds_proxy_requests_total.inc()
    worlds_proxy_requests_total._val = worlds_proxy_requests_total._value.get()  # type: ignore[attr-defined]
    _update_worlds_cache_ratio()


def record_worlds_cache_hit() -> None:
    """Record a cache hit for WorldService proxy."""
    worlds_cache_hits_total.inc()
    worlds_cache_hits_total._val = worlds_cache_hits_total._value.get()  # type: ignore[attr-defined]
    _update_worlds_cache_ratio()


def record_worlds_stale_response() -> None:
    """Record serving a stale WorldService cache entry."""
    worlds_stale_responses_total.inc()
    worlds_stale_responses_total._val = worlds_stale_responses_total._value.get()  # type: ignore[attr-defined]


def _update_worlds_cache_ratio() -> None:
    total = worlds_cache_hits_total._value.get() + worlds_proxy_requests_total._value.get()
    ratio = worlds_cache_hits_total._value.get() / total if total else 0
    worlds_cache_hit_ratio.set(ratio)
    worlds_cache_hit_ratio._val = worlds_cache_hit_ratio._value.get()  # type: ignore[attr-defined]


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
    ws_subscribers._vals = {}  # type: ignore[attr-defined]
    for topic, count in counts.items():
        ws_subscribers.labels(topic=topic).set(count)
        ws_subscribers._vals[topic] = count  # type: ignore[attr-defined]


def record_ws_drop(count: int = 1) -> None:
    """Increment dropped subscriber counter."""
    ws_dropped_subscribers_total.inc(count)


def start_metrics_server(port: int = 8000) -> None:
    """Start an HTTP server to expose metrics."""
    start_http_server(port, registry=global_registry)


def collect_metrics() -> str:
    """Return metrics in text exposition format."""
    return generate_latest(global_registry).decode()


def reset_metrics() -> None:
    """Reset all metric values for tests."""
    reset_registered_metrics(_REGISTERED_METRICS)
    _e2e_samples.clear()
    _worlds_samples.clear()
    _sentinel_weight_updates.clear()
