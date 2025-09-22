"""Utilities for normalising execution domains and world node statuses."""

from __future__ import annotations

from .constants import (
    DEFAULT_EXECUTION_DOMAIN,
    DEFAULT_WORLD_NODE_STATUS,
    EXECUTION_DOMAINS,
    WORLD_NODE_STATUSES,
)


def _normalize_execution_domain(execution_domain: str | None) -> str:
    """Normalise *execution_domain* to a canonical, validated value."""

    if execution_domain is None:
        return DEFAULT_EXECUTION_DOMAIN
    candidate = str(execution_domain).strip().lower()
    if not candidate:
        return DEFAULT_EXECUTION_DOMAIN
    if candidate not in EXECUTION_DOMAINS:
        raise ValueError(f"unknown execution_domain: {execution_domain}")
    return candidate


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
