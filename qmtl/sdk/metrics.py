from __future__ import annotations

"""Prometheus metrics for the SDK cache layer."""

import time
from prometheus_client import Counter, Gauge, generate_latest, start_http_server, REGISTRY as global_registry

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


def observe_cache_read(upstream_id: str, interval: int) -> None:
    """Increment read metrics for a given upstream/interval pair."""
    u = str(upstream_id)
    i = str(interval)
    cache_read_total.labels(upstream_id=u, interval=i).inc()
    cache_read_total._vals[(u, i)] = cache_read_total._vals.get((u, i), 0) + 1  # type: ignore[attr-defined]
    ts = time.time()
    cache_last_read_timestamp.labels(upstream_id=u, interval=i).set(ts)
    cache_last_read_timestamp._vals[(u, i)] = ts  # type: ignore[attr-defined]


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
