from __future__ import annotations

"""Utilities for Kafka topic naming and configuration."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TopicConfig:
    partitions: int
    replication_factor: int
    retention_ms: int


_QUEUE_CONFIG = {
    "raw": TopicConfig(partitions=3, replication_factor=3, retention_ms=7 * 24 * 60 * 60 * 1000),
    "indicator": TopicConfig(partitions=1, replication_factor=2, retention_ms=30 * 24 * 60 * 60 * 1000),
    "trade_exec": TopicConfig(partitions=1, replication_factor=3, retention_ms=90 * 24 * 60 * 60 * 1000),
}


def topic_name(asset: str, node_type: str, code_hash: str, version: str, *, dryrun: bool = False) -> str:
    """Return topic name following `{asset}_{node_type}_{short_hash}_{version}`."""
    short_hash = code_hash[:6]
    suffix = "_sim" if dryrun else ""
    return f"{asset}_{node_type}_{short_hash}_{version}{suffix}"


def get_config(queue_type: str) -> TopicConfig:
    """Return :class:`TopicConfig` for the given ``queue_type``."""
    try:
        return _QUEUE_CONFIG[queue_type]
    except KeyError:
        raise ValueError(f"unknown queue type: {queue_type}")


__all__ = ["TopicConfig", "topic_name", "get_config"]
