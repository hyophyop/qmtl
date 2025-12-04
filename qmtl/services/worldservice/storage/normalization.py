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

    - Accepts canonical tokens (backtest | dryrun | live | shadow) and maps
      known aliases via ``resolve_execution_domain``.
    - Missing/empty/default values downgrade to the default compute-only domain.
    - Unknown tokens raise to avoid silently running in an unintended domain.
    """

    raw = "" if execution_domain is None else str(execution_domain).strip()
    if not raw or raw.lower() == "default":
        return DEFAULT_EXECUTION_DOMAIN

    resolved = resolve_execution_domain(raw)
    if resolved is None:
        allowed = ", ".join(sorted(EXECUTION_DOMAINS))
        raise ValueError(f"unknown execution_domain '{execution_domain}'; expected one of {allowed}")

    candidate = resolved.strip().lower()
    if not candidate or candidate == "default":
        return DEFAULT_EXECUTION_DOMAIN
    if candidate in EXECUTION_DOMAINS:
        return candidate

    allowed = ", ".join(sorted(EXECUTION_DOMAINS))
    raise ValueError(f"unknown execution_domain '{execution_domain}'; expected one of {allowed}")


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
