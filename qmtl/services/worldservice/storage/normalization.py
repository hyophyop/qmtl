"""Utilities for normalising execution domains and world node statuses."""

from __future__ import annotations

from qmtl.foundation.common.compute_context import resolve_execution_domain

from .constants import (
    DEFAULT_EXECUTION_DOMAIN,
    DEFAULT_WORLD_NODE_STATUS,
    EXECUTION_DOMAINS,
    WORLD_NODE_STATUSES,
)


def _normalize_execution_domain(execution_domain: str | None) -> str:
    """Normalise *execution_domain* to a canonical, validated value.

    - Missing/empty/default values are downgraded to the default compute-only domain.
    - Common aliases (compute-only/compute_only, paper/sim, prod/live) are mapped
      via ``resolve_execution_domain``.
    - Unknown tokens surface a clear error so callers can fix inputs instead of
      silently running in an unintended domain.
    """

    if execution_domain is None:
        return DEFAULT_EXECUTION_DOMAIN

    raw = str(execution_domain).strip()
    if not raw:
        return DEFAULT_EXECUTION_DOMAIN

    resolved = resolve_execution_domain(raw)
    if resolved is None or resolved.strip().lower() in {"", "default"}:
        return DEFAULT_EXECUTION_DOMAIN

    candidate = resolved.strip().lower()
    if candidate == DEFAULT_EXECUTION_DOMAIN:
        return DEFAULT_EXECUTION_DOMAIN
    if candidate in EXECUTION_DOMAINS:
        return candidate

    allowed = ", ".join(sorted(EXECUTION_DOMAINS))
    raise ValueError(
        f"unknown execution_domain '{execution_domain}'; expected one of {allowed} "
        "(aliases like 'compute-only' -> backtest, 'paper/sim' -> dryrun)"
    )


def _normalize_world_node_status(status: str | None) -> str:
    """Normalise *status* to one of the known world node states."""

    if status is None:
        return DEFAULT_WORLD_NODE_STATUS
    candidate = str(status).strip().lower()
    if not candidate:
        return DEFAULT_WORLD_NODE_STATUS
    if candidate not in WORLD_NODE_STATUSES:
        raise ValueError(f"unknown world node status: {status}")
    return candidate


__all__ = ["_normalize_execution_domain", "_normalize_world_node_status"]
