from __future__ import annotations

"""Prometheus metrics for Gateway."""

from collections import deque
from typing import Deque
import time

from prometheus_client import (
    Gauge,
    Counter,
    generate_latest,
    start_http_server,
    REGISTRY as global_registry,
)

_e2e_samples: Deque[float] = deque(maxlen=100)
_worlds_samples: Deque[float] = deque(maxlen=100)
_sentinel_weight_updates: dict[str, float] = {}

gateway_e2e_latency_p95 = Gauge(
    "gateway_e2e_latency_p95",
    "95th percentile end-to-end latency in milliseconds",
    registry=global_registry,
)

lost_requests_total = Counter(
    "lost_requests_total",
    "Total number of diff submissions lost due to queue errors",
    registry=global_registry,
)

dagclient_breaker_state = Gauge(
    "dagclient_breaker_state",
    "DAG Manager circuit breaker state (1=open, 0=closed)",
    registry=global_registry,
)

dagclient_breaker_failures = Gauge(
    "dagclient_breaker_failures",
    "Consecutive failures recorded by the DAG Manager circuit breaker",
    registry=global_registry,
)

dagclient_breaker_open_total = Gauge(
    "dagclient_breaker_open_total",
    "Number of times the DAG Manager client breaker opened",
    registry=global_registry,
)

# Metrics for WorldService proxy
worlds_proxy_latency_p95 = Gauge(
    "worlds_proxy_latency_p95",
    "95th percentile latency of requests proxied to WorldService in milliseconds",
    registry=global_registry,
)

worlds_proxy_requests_total = Counter(
    "worlds_proxy_requests_total",
    "Total number of requests proxied to WorldService",
    registry=global_registry,
)

worlds_cache_hits_total = Counter(
    "worlds_cache_hits_total",
    "Total number of cache hits when proxying WorldService requests",
    registry=global_registry,
)

worlds_cache_hit_ratio = Gauge(
    "worlds_cache_hit_ratio",
    "Cache hit ratio for WorldService proxy requests",
    registry=global_registry,
)

worlds_stale_responses_total = Counter(
    "worlds_stale_responses_total",
    "Total number of stale cache responses served for WorldService requests",
    registry=global_registry,
)

# Circuit breaker metrics for WorldService
worlds_breaker_state = Gauge(
    "worlds_breaker_state",
    "WorldService circuit breaker state (1=open, 0=closed)",
    registry=global_registry,
)

worlds_breaker_failures = Gauge(
    "worlds_breaker_failures",
    "Consecutive failures recorded by the WorldService circuit breaker",
    registry=global_registry,
)

worlds_breaker_open_total = Gauge(
    "worlds_breaker_open_total",
    "Number of times the WorldService client breaker opened",
    registry=global_registry,
)


# Track the percentage of traffic routed to each sentinel version
if "gateway_sentinel_traffic_ratio" in global_registry._names_to_collectors:
    gateway_sentinel_traffic_ratio = global_registry._names_to_collectors["gateway_sentinel_traffic_ratio"]
else:
    gateway_sentinel_traffic_ratio = Gauge(
        "gateway_sentinel_traffic_ratio",
        "Traffic ratio reported by each sentinel instance (0~1)",
        ["sentinel_id"],
        registry=global_registry,
    )
gateway_sentinel_traffic_ratio._vals = {}  # type: ignore[attr-defined]

# Degradation level of the Gateway service
degrade_level = Gauge(
    "degrade_level",
    "Current degradation level",
    ["service"],
    registry=global_registry,
)

# Event relay and ControlBus metrics
controlbus_lag_ms = Gauge(
    "controlbus_lag_ms",
    "Delay between event creation and processing in milliseconds",
    ["topic"],
    registry=global_registry,
)

event_relay_events_total = Counter(
    "event_relay_events_total",
    "Total number of ControlBus events relayed to clients",
    ["topic"],
    registry=global_registry,
)

event_relay_dropped_total = Counter(
    "event_relay_dropped_total",
    "Total number of ControlBus events dropped",
    ["topic"],
    registry=global_registry,
)

event_relay_skew_ms = Gauge(
    "event_relay_skew_ms",
    "Clock skew between event timestamp and relay time in milliseconds",
    ["topic"],
    registry=global_registry,
)

event_fanout_total = Counter(
    "event_fanout_total",
    "Total number of recipients for relayed ControlBus events",
    ["topic"],
    registry=global_registry,
)

ws_subscribers = Gauge(
    "ws_subscribers",
    "Active WebSocket subscribers",
    ["topic"],
    registry=global_registry,
)
ws_subscribers._vals = {}  # type: ignore[attr-defined]

ws_dropped_subscribers_total = Counter(
    "ws_dropped_subscribers_total",
    "Total number of WebSocket subscribers dropped",
    registry=global_registry,
)

sentinel_skew_seconds = Gauge(
    "sentinel_skew_seconds",
    "Seconds between sentinel weight update and observed traffic ratio",
    ["sentinel_id"],
    registry=global_registry,
)
sentinel_skew_seconds._vals = {}  # type: ignore[attr-defined]


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


def record_sentinel_weight_update(sentinel_id: str) -> None:
    """Record the time when a sentinel weight update was received."""
    _sentinel_weight_updates[sentinel_id] = time.time()


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
    _e2e_samples.clear()
    gateway_e2e_latency_p95.set(0)
    gateway_e2e_latency_p95._val = 0  # type: ignore[attr-defined]
    lost_requests_total._value.set(0)  # type: ignore[attr-defined]
    lost_requests_total._val = 0  # type: ignore[attr-defined]
    gateway_sentinel_traffic_ratio.clear()
    gateway_sentinel_traffic_ratio._vals = {}  # type: ignore[attr-defined]
    if hasattr(gateway_sentinel_traffic_ratio, "_metrics"):
        gateway_sentinel_traffic_ratio._metrics.clear()
    dagclient_breaker_state.set(0)
    dagclient_breaker_state._val = 0  # type: ignore[attr-defined]
    dagclient_breaker_failures.set(0)
    dagclient_breaker_failures._val = 0  # type: ignore[attr-defined]
    degrade_level.clear()
    dagclient_breaker_open_total.set(0)
    dagclient_breaker_open_total._val = 0  # type: ignore[attr-defined]
    worlds_proxy_latency_p95.set(0)
    worlds_proxy_latency_p95._val = 0  # type: ignore[attr-defined]
    worlds_proxy_requests_total._value.set(0)  # type: ignore[attr-defined]
    worlds_proxy_requests_total._val = 0  # type: ignore[attr-defined]
    worlds_cache_hits_total._value.set(0)  # type: ignore[attr-defined]
    worlds_cache_hits_total._val = 0  # type: ignore[attr-defined]
    worlds_cache_hit_ratio.set(0)
    worlds_cache_hit_ratio._val = 0  # type: ignore[attr-defined]
    worlds_stale_responses_total._value.set(0)  # type: ignore[attr-defined]
    worlds_stale_responses_total._val = 0  # type: ignore[attr-defined]
    _worlds_samples.clear()
    worlds_breaker_state.set(0)
    worlds_breaker_state._val = 0  # type: ignore[attr-defined]
    worlds_breaker_failures.set(0)
    worlds_breaker_failures._val = 0  # type: ignore[attr-defined]
    worlds_breaker_open_total.set(0)
    worlds_breaker_open_total._val = 0  # type: ignore[attr-defined]
    _sentinel_weight_updates.clear()
    controlbus_lag_ms.clear()
    event_relay_events_total.clear()
    event_relay_dropped_total.clear()
    event_relay_skew_ms.clear()
    event_fanout_total.clear()
    ws_subscribers.clear()
    ws_subscribers._vals = {}  # type: ignore[attr-defined]
    ws_dropped_subscribers_total._value.set(0)  # type: ignore[attr-defined]
    ws_dropped_subscribers_total._val = 0  # type: ignore[attr-defined]
    sentinel_skew_seconds.clear()
    sentinel_skew_seconds._vals = {}  # type: ignore[attr-defined]

