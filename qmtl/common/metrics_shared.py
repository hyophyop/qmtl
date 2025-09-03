from __future__ import annotations

"""Shared helpers for Prometheus metrics used across SDK and DAG Manager.

This module centralizes creation and observation of common metrics to avoid
duplicate registration when both subsystems are imported in the same process.
"""

from prometheus_client import Gauge, REGISTRY as global_registry

__all__ = [
    "get_nodecache_resident_bytes",
    "observe_nodecache_resident_bytes",
    "clear_nodecache_resident_bytes",
]


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

