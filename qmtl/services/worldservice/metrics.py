from __future__ import annotations

"""Prometheus metrics for WorldService apply and allocation flows."""

from collections.abc import MutableMapping
from datetime import datetime, timezone
from typing import Any, Mapping, cast

from qmtl.foundation.common.metrics_factory import (
    get_mapping_store,
    get_metric_value,
    get_or_create_counter,
    get_or_create_gauge,
    get_or_create_histogram,
    reset_metrics as reset_registered_metrics,
)

_REGISTERED_METRICS: set[str] = set()


def _metric_store(metric: object) -> MutableMapping[Any, Any]:
    return get_mapping_store(cast(Any, metric), dict)


def _counter(name: str, documentation: str, labelnames: tuple[str, ...] | None = None):
    metric = get_or_create_counter(name, documentation, labelnames)
    _REGISTERED_METRICS.add(getattr(metric, "_name", name))
    return metric


def _gauge(name: str, documentation: str, labelnames: tuple[str, ...] | None = None):
    metric = get_or_create_gauge(name, documentation, labelnames)
    _REGISTERED_METRICS.add(getattr(metric, "_name", name))
    return metric


def _histogram(name: str, documentation: str, labelnames: tuple[str, ...] | None = None):
    metric = get_or_create_histogram(name, documentation, labelnames)
    _REGISTERED_METRICS.add(getattr(metric, "_name", name))
    return metric


world_apply_run_total = _counter(
    "world_apply_run_total",
    "Total number of apply runs grouped by outcome",
    ("world_id", "run_id", "status"),
)

world_apply_failure_total = _counter(
    "world_apply_failure_total",
    "Total number of failed apply runs",
    ("world_id", "run_id", "stage"),
)

world_allocation_snapshot_total = _counter(
    "world_allocation_snapshot_total",
    "Total allocation snapshots served",
    ("world_id",),
)

world_allocation_snapshot_stale_total = _counter(
    "world_allocation_snapshot_stale_total",
    "Total stale allocation snapshots served",
    ("world_id",),
)

world_allocation_snapshot_stale_ratio = _gauge(
    "world_allocation_snapshot_stale_ratio",
    "Ratio of stale allocation snapshots over total",
    ("world_id",),
)

risk_hub_snapshot_dedupe_total = _counter(
    "risk_hub_snapshot_dedupe_total",
    "Risk hub snapshots dropped due to dedupe key collisions",
    ("world_id", "stage"),
)

risk_hub_snapshot_expired_total = _counter(
    "risk_hub_snapshot_expired_total",
    "Risk hub snapshots dropped because ttl_sec was exceeded",
    ("world_id", "stage"),
)

risk_hub_snapshot_processed_total = _counter(
    "risk_hub_snapshot_processed_total",
    "Risk hub snapshots successfully applied from ControlBus",
    ("world_id", "stage"),
)

risk_hub_snapshot_failed_total = _counter(
    "risk_hub_snapshot_failed_total",
    "Risk hub snapshots that failed to process from ControlBus",
    ("world_id", "stage"),
)

risk_hub_snapshot_retry_total = _counter(
    "risk_hub_snapshot_retry_total",
    "Risk hub snapshot processing retries from ControlBus",
    ("world_id", "stage"),
)

risk_hub_snapshot_dlq_total = _counter(
    "risk_hub_snapshot_dlq_total",
    "Risk hub snapshots routed to DLQ after retries",
    ("world_id", "stage"),
)

risk_hub_snapshot_processing_latency_seconds = _histogram(
    "risk_hub_snapshot_processing_latency_seconds",
    "Time between snapshot creation and WS processing",
    ("world_id", "stage"),
)


def _update_snapshot_ratio(world_id: str) -> None:
    total = get_metric_value(
        world_allocation_snapshot_total, {"world_id": world_id}
    )
    stale = get_metric_value(
        world_allocation_snapshot_stale_total, {"world_id": world_id}
    )
    ratio = stale / total if total else 0.0
    world_allocation_snapshot_stale_ratio.labels(world_id=world_id).set(ratio)
    _metric_store(world_allocation_snapshot_stale_ratio)[world_id] = ratio


def record_apply_run_started(world_id: str, run_id: str) -> None:
    """Record that an apply run began processing."""

    world_apply_run_total.labels(world_id=world_id, run_id=run_id, status="started").inc()


def record_apply_run_completed(world_id: str, run_id: str) -> None:
    """Record successful completion of an apply run."""

    world_apply_run_total.labels(world_id=world_id, run_id=run_id, status="success").inc()


def record_apply_run_failed(world_id: str, run_id: str, *, stage: str | None = None) -> None:
    """Record a failed apply run and its last known stage."""

    stage_label = stage or "unknown"
    world_apply_run_total.labels(world_id=world_id, run_id=run_id, status="failure").inc()
    world_apply_failure_total.labels(world_id=world_id, run_id=run_id, stage=stage_label).inc()


def record_allocation_snapshot(world_id: str, *, stale: bool) -> None:
    """Record snapshot freshness for a world allocation payload."""

    world_allocation_snapshot_total.labels(world_id=world_id).inc()
    if stale:
        world_allocation_snapshot_stale_total.labels(world_id=world_id).inc()
    _update_snapshot_ratio(world_id)


def record_risk_snapshot_dedupe(world_id: str, *, stage: str | None = None) -> None:
    """Record when an incoming risk snapshot was skipped due to dedupe."""

    risk_hub_snapshot_dedupe_total.labels(
        world_id=world_id,
        stage=stage or "unknown",
    ).inc()


def record_risk_snapshot_expired(world_id: str, *, stage: str | None = None) -> None:
    """Record when an incoming risk snapshot was skipped because it expired."""

    risk_hub_snapshot_expired_total.labels(
        world_id=world_id,
        stage=stage or "unknown",
    ).inc()


def record_risk_snapshot_processed(
    world_id: str,
    *,
    stage: str | None = None,
    latency_seconds: float | None = None,
) -> None:
    """Record successful processing of a risk snapshot."""

    stage_label = stage or "unknown"
    risk_hub_snapshot_processed_total.labels(world_id=world_id, stage=stage_label).inc()
    if latency_seconds is not None:
        risk_hub_snapshot_processing_latency_seconds.labels(
            world_id=world_id, stage=stage_label
        ).observe(float(latency_seconds))


def record_risk_snapshot_failed(world_id: str, *, stage: str | None = None) -> None:
    """Record failed processing of a risk snapshot."""

    risk_hub_snapshot_failed_total.labels(
        world_id=world_id,
        stage=stage or "unknown",
    ).inc()


def record_risk_snapshot_retry(world_id: str, *, stage: str | None = None) -> None:
    """Record a retry attempt while processing a risk snapshot."""

    risk_hub_snapshot_retry_total.labels(
        world_id=world_id,
        stage=stage or "unknown",
    ).inc()


def record_risk_snapshot_dlq(world_id: str, *, stage: str | None = None) -> None:
    """Record when a risk snapshot is routed to DLQ after failures."""

    risk_hub_snapshot_dlq_total.labels(
        world_id=world_id,
        stage=stage or "unknown",
    ).inc()


def parse_timestamp(value: str | None) -> datetime | None:
    """Parse ISO8601 timestamps, normalizing to UTC."""

    if not value:
        return None
    try:
        ts = datetime.fromisoformat(value)
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def reset_metrics() -> None:
    """Reset metrics for tests."""

    reset_registered_metrics(_REGISTERED_METRICS)
    for metric in (
        world_allocation_snapshot_total,
        world_allocation_snapshot_stale_total,
        world_allocation_snapshot_stale_ratio,
        world_apply_run_total,
        world_apply_failure_total,
        risk_hub_snapshot_dedupe_total,
        risk_hub_snapshot_expired_total,
        risk_hub_snapshot_processed_total,
        risk_hub_snapshot_failed_total,
        risk_hub_snapshot_retry_total,
        risk_hub_snapshot_dlq_total,
        risk_hub_snapshot_processing_latency_seconds,
    ):
        if hasattr(metric, "_metrics"):
            cast(Any, metric)._metrics.clear()
        _metric_store(metric).clear()


__all__ = [
    "parse_timestamp",
    "record_allocation_snapshot",
    "record_apply_run_completed",
    "record_apply_run_failed",
    "record_apply_run_started",
    "record_risk_snapshot_dedupe",
    "record_risk_snapshot_expired",
    "record_risk_snapshot_processed",
    "record_risk_snapshot_failed",
    "record_risk_snapshot_retry",
    "record_risk_snapshot_dlq",
    "reset_metrics",
    "risk_hub_snapshot_dedupe_total",
    "risk_hub_snapshot_expired_total",
    "risk_hub_snapshot_processed_total",
    "risk_hub_snapshot_failed_total",
    "risk_hub_snapshot_retry_total",
    "risk_hub_snapshot_dlq_total",
    "risk_hub_snapshot_processing_latency_seconds",
    "world_allocation_snapshot_stale_ratio",
    "world_allocation_snapshot_total",
    "world_allocation_snapshot_stale_total",
    "world_apply_failure_total",
    "world_apply_run_total",
]
