from __future__ import annotations

"""Shared helpers for Prometheus metrics used across SDK and DAG Manager.

This module centralizes creation and observation of common metrics to avoid
duplicate registration when both subsystems are imported in the same process.
"""

from qmtl.foundation.common.metrics_factory import (
    get_or_create_counter,
    get_or_create_gauge,
    reset_metrics,
)

__all__ = [
    "get_nodecache_resident_bytes",
    "observe_nodecache_resident_bytes",
    "clear_nodecache_resident_bytes",
    "get_cross_context_cache_hit_counter",
    "observe_cross_context_cache_hit",
    "clear_cross_context_cache_hits",
]

_UNSET_LABEL = "__unset__"


def get_nodecache_resident_bytes():
    """Return the singleton Gauge for node cache residency bytes.

    Ensures a consistent instance and attaches an internal ``_vals`` store
    used by tests in both SDK and DAG Manager modules.
    """
    return get_or_create_gauge(
        "nodecache_resident_bytes",
        "Resident bytes held in node caches",
        ["node_id", "scope"],
        test_value_attr="_vals",
        test_value_factory=dict,
    )


def observe_nodecache_resident_bytes(node_id: str, resident: int) -> None:
    """Record per-node and aggregate resident byte counts.

    Mirrors historical behavior from both SDK and DAG Manager metrics modules.
    """
    g = get_nodecache_resident_bytes()
    n = str(node_id)
    g.labels(node_id=n, scope="node").set(resident)
    g._vals[(n, "node")] = resident  # type: ignore[attr-defined]
    total = sum(v for (nid, sc), v in g._vals.items() if sc == "node")  # type: ignore[attr-defined]
    g.labels(node_id="all", scope="total").set(total)
    g._vals[("all", "total")] = total  # type: ignore[attr-defined]


def clear_nodecache_resident_bytes() -> None:
    reset_metrics(["nodecache_resident_bytes"])


def get_cross_context_cache_hit_counter():
    """Return the singleton counter tracking cross-context cache hits."""

    expected_labels = [
        "node_id",
        "world_id",
        "execution_domain",
        "as_of",
        "partition",
    ]
    return get_or_create_counter(
        "cross_context_cache_hit_total",
        "Number of cache hits observed with mismatched context",
        expected_labels,
        test_value_attr="_vals",
        test_value_factory=dict,
    )


def _normalise(value: str | None) -> str:
    value = _UNSET_LABEL if value in (None, "") else value
    return str(value)


def observe_cross_context_cache_hit(
    node_id: str,
    world_id: str,
    execution_domain: str,
    *,
    as_of: str | None = None,
    partition: str | None = None,
) -> None:
    """Increment the cross-context cache hit counter with normalized labels."""

    counter = get_cross_context_cache_hit_counter()
    labels = dict(
        node_id=str(node_id),
        world_id=str(world_id),
        execution_domain=str(execution_domain),
        as_of=_normalise(as_of),
        partition=_normalise(partition),
    )
    counter.labels(**labels).inc()
    key = tuple(labels.values())
    counter._vals[key] = counter._vals.get(key, 0) + 1  # type: ignore[attr-defined]


def clear_cross_context_cache_hits() -> None:
    reset_metrics(["cross_context_cache_hit_total"])
