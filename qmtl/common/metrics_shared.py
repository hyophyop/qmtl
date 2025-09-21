from __future__ import annotations

"""Shared helpers for Prometheus metrics used across SDK and DAG Manager.

This module centralizes creation and observation of common metrics to avoid
duplicate registration when both subsystems are imported in the same process.
"""

from prometheus_client import Counter, Gauge, REGISTRY as global_registry

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
    if "nodecache_resident_bytes" in global_registry._names_to_collectors:  # type: ignore[attr-defined]
        g = global_registry._names_to_collectors["nodecache_resident_bytes"]  # type: ignore[index]
    else:
        g = Gauge(
            "nodecache_resident_bytes",
            "Resident bytes held in node caches",
            ["node_id", "scope"],
            registry=global_registry,
        )
    # Attach test-visible storage if not present
    if not hasattr(g, "_vals"):
        g._vals = {}  # type: ignore[attr-defined]
    return g


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
    g = get_nodecache_resident_bytes()
    g.clear()
    g._vals = {}  # type: ignore[attr-defined]


def get_cross_context_cache_hit_counter():
    """Return the singleton counter tracking cross-context cache hits."""

    expected_labels = [
        "node_id",
        "world_id",
        "execution_domain",
        "as_of",
        "partition",
    ]
    if "cross_context_cache_hit_total" in global_registry._names_to_collectors:  # type: ignore[attr-defined]
        counter = global_registry._names_to_collectors["cross_context_cache_hit_total"]  # type: ignore[index]
        try:
            labelnames = list(counter._labelnames)  # type: ignore[attr-defined]
        except Exception:
            labelnames = expected_labels
        if labelnames != expected_labels:
            global_registry.unregister(counter)
            counter = Counter(
                "cross_context_cache_hit_total",
                "Number of cache hits observed with mismatched context",
                expected_labels,
                registry=global_registry,
            )
    else:
        counter = Counter(
            "cross_context_cache_hit_total",
            "Number of cache hits observed with mismatched context",
            expected_labels,
            registry=global_registry,
        )

    if not hasattr(counter, "_vals"):
        counter._vals = {}  # type: ignore[attr-defined]
    return counter


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
    counter = get_cross_context_cache_hit_counter()
    counter.clear()
    counter._vals = {}  # type: ignore[attr-defined]
