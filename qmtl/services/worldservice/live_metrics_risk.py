"""Prometheus-friendly gauges/counters for Risk Hub health."""

from __future__ import annotations

from prometheus_client import Counter, Gauge

risk_hub_snapshot_lag_seconds = Gauge(
    "risk_hub_snapshot_lag_seconds",
    "Age in seconds of the latest risk hub snapshot",
    ["world_id"],
)

risk_hub_snapshot_missing_total = Counter(
    "risk_hub_snapshot_missing_total",
    "Count of missing/failed risk hub snapshots",
    ["world_id"],
)

__all__ = [
    "risk_hub_snapshot_lag_seconds",
    "risk_hub_snapshot_missing_total",
]
