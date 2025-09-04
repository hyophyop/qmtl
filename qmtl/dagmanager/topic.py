from __future__ import annotations

"""Utilities for Kafka topic naming and configuration."""

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class TopicConfig:
    partitions: int
    replication_factor: int
    retention_ms: int


_TOPIC_CONFIG = {
    "raw": TopicConfig(partitions=3, replication_factor=3, retention_ms=7 * 24 * 60 * 60 * 1000),
    "indicator": TopicConfig(partitions=1, replication_factor=2, retention_ms=30 * 24 * 60 * 60 * 1000),
    "trade_exec": TopicConfig(partitions=1, replication_factor=3, retention_ms=90 * 24 * 60 * 60 * 1000),
}


def topic_name(
    asset: str,
    node_type: str,
    code_hash: str,
    version: str,
    *,
    dry_run: bool = False,
    existing: Iterable[str] | None = None,
) -> str:
    """Return unique topic name per spec.

    The name follows ``{asset}_{node_type}_{short_hash}_{version}{_sim?}`` where
    ``short_hash`` initially uses the first six characters of ``code_hash`` and
    grows by two characters until the name is unique within ``existing``.
    """

    taken = set(existing or [])
    length = 6
    suffix = "_sim" if dry_run else ""

    # First try by growing the short hash up to the full hash length
    while length <= len(code_hash):
        short_hash = code_hash[:length]
        name = f"{asset}_{node_type}_{short_hash}_{version}{suffix}"
        if name not in taken:
            return name
        length += 2

    # Fall back to numeric suffix if all hash-length attempts collide
    base = f"{asset}_{node_type}_{code_hash}_{version}{suffix}"
    if base not in taken:
        return base
    for n in range(1, 10000):
        candidate = f"{base}-{n}"
        if candidate not in taken:
            return candidate
    # As a final guard, raise to avoid infinite loops
    raise RuntimeError("unable to generate unique topic name after 10k attempts")


def get_config(topic_type: str) -> TopicConfig:
    """Return :class:`TopicConfig` for the given ``topic_type``."""
    try:
        return _TOPIC_CONFIG[topic_type]
    except KeyError:
        raise ValueError(f"unknown topic type: {topic_type}")


__all__ = ["TopicConfig", "topic_name", "get_config"]
