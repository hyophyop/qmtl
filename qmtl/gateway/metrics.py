from __future__ import annotations

"""Prometheus metrics for Gateway."""

from collections import deque
from typing import Deque
import time

from prometheus_client import Gauge, Counter, generate_latest, start_http_server, REGISTRY as global_registry

_e2e_samples: Deque[float] = deque(maxlen=100)

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
    "DAG manager circuit breaker state (1=open, 0=closed)",
    registry=global_registry,
)

dagclient_breaker_failures = Gauge(
    "dagclient_breaker_failures",
    "Consecutive failures recorded by the DAG manager circuit breaker",
    registry=global_registry,
)

dagclient_breaker_open_total = Gauge(
    "dagclient_breaker_open_total",
    "Number of times the DAG manager client breaker opened",
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


def set_sentinel_traffic_ratio(sentinel_id: str, ratio: float) -> None:
    """Update the live traffic ratio for a sentinel version."""
    gateway_sentinel_traffic_ratio.labels(sentinel_id=sentinel_id).set(ratio)
    gateway_sentinel_traffic_ratio._vals[sentinel_id] = ratio  # type: ignore[attr-defined]


def observe_gateway_latency(duration_ms: float) -> None:
    """Record a request latency and update the p95 gauge."""
    _e2e_samples.append(duration_ms)
    if not _e2e_samples:
        return
    ordered = sorted(_e2e_samples)
    idx = max(0, int(len(ordered) * 0.95) - 1)
    gateway_e2e_latency_p95.set(ordered[idx])
    gateway_e2e_latency_p95._val = gateway_e2e_latency_p95._value.get()  # type: ignore[attr-defined]


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

