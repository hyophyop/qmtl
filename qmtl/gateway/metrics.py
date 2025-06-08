from __future__ import annotations

"""Prometheus metrics for Gateway."""

from collections import deque
from typing import Deque
import time

from prometheus_client import Gauge, Counter, CollectorRegistry, generate_latest, start_http_server

registry = CollectorRegistry()

_e2e_samples: Deque[float] = deque(maxlen=100)

gateway_e2e_latency_p95 = Gauge(
    "gateway_e2e_latency_p95",
    "95th percentile end-to-end latency in milliseconds",
    registry=registry,
)

lost_requests_total = Counter(
    "lost_requests_total",
    "Total number of diff submissions lost due to queue errors",
    registry=registry,
)


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
    start_http_server(port, registry=registry)


def collect_metrics() -> str:
    """Return metrics in text exposition format."""
    return generate_latest(registry).decode()


def reset_metrics() -> None:
    """Reset all metric values for tests."""
    _e2e_samples.clear()
    gateway_e2e_latency_p95.set(0)
    gateway_e2e_latency_p95._val = 0  # type: ignore[attr-defined]
    lost_requests_total._value.set(0)  # type: ignore[attr-defined]
    lost_requests_total._val = 0  # type: ignore[attr-defined]
