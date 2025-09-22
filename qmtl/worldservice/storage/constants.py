"""Shared constants for WorldService storage repositories."""

from __future__ import annotations

WORLD_NODE_STATUSES: set[str] = {
    "unknown",
    "validating",
    "valid",
    "invalid",
    "running",
    "paused",
    "stopped",
    "archived",
}

EXECUTION_DOMAINS: set[str] = {"backtest", "dryrun", "live", "shadow"}
DEFAULT_EXECUTION_DOMAIN = "live"
DEFAULT_WORLD_NODE_STATUS = "unknown"

DEFAULT_EDGE_OVERRIDES: tuple[tuple[str, str, str]] = (
    ("domain:backtest", "domain:live", "auto:cross-domain-block"),
)

__all__ = [
    "DEFAULT_EDGE_OVERRIDES",
    "DEFAULT_EXECUTION_DOMAIN",
    "DEFAULT_WORLD_NODE_STATUS",
    "EXECUTION_DOMAINS",
    "WORLD_NODE_STATUSES",
]
