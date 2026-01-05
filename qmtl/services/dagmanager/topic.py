from __future__ import annotations

"""Utilities for Kafka topic naming and configuration."""

from dataclasses import dataclass
from typing import Iterable, Mapping


_NAMESPACE_ENABLED: bool = True


def set_topic_namespace_enabled(enabled: bool) -> None:
    """Set the global topic-namespace guard flag."""

    global _NAMESPACE_ENABLED
    _NAMESPACE_ENABLED = bool(enabled)


def topic_namespace_enabled() -> bool:
    """Return ``True`` when topic namespace prefixing is enabled."""

    return _NAMESPACE_ENABLED


def _sanitize_namespace_segment(value: object) -> str:
    """Return a Kafka-safe namespace segment."""

    if not isinstance(value, str):
        return ""
    cleaned: list[str] = []
    for ch in value.strip():
        if ch.isalnum():
            cleaned.append(ch.lower())
        elif ch in {"-", "_"}:
            cleaned.append(ch)
        elif ch == ".":
            # Dots separate segments; normalise to hyphen inside a segment
            cleaned.append("-")
        else:
            cleaned.append("-")
    result = "".join(cleaned).strip("-_")
    return result


def _sanitize_namespace(value: object) -> str | None:
    if isinstance(value, str):
        parts = [_sanitize_namespace_segment(part) for part in value.split(".")]
    elif isinstance(value, Mapping):
        world = value.get("world") or value.get("world_id")
        domain = value.get("domain") or value.get("execution_domain")
        parts = [_sanitize_namespace_segment(world), _sanitize_namespace_segment(domain)]
    else:
        return None
    filtered = [part for part in parts if part]
    if not filtered:
        return None
    return ".".join(filtered)


def build_namespace(world: object | None, domain: object | None) -> str | None:
    """Return ``"world.domain"`` namespace when both segments are valid."""

    world_part = _sanitize_namespace_segment(world)
    domain_part = _sanitize_namespace_segment(domain)
    if not world_part or not domain_part:
        return None
    return f"{world_part}.{domain_part}"


def normalize_namespace(namespace: object | None) -> str | None:
    """Normalise namespace input (string or mapping) to ``world.domain``."""

    if namespace is None:
        return None
    if isinstance(namespace, Mapping):
        return build_namespace(
            namespace.get("world") or namespace.get("world_id"),
            namespace.get("domain") or namespace.get("execution_domain"),
        )
    return _sanitize_namespace(namespace)


def ensure_namespace(topic: str, namespace: object | None) -> str:
    """Return ``topic`` prefixed with ``namespace`` when provided."""

    normalized = normalize_namespace(namespace)
    if not normalized:
        return topic
    prefix = f"{normalized}."
    if topic.startswith(prefix):
        return topic
    return prefix + topic


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


def _node_id_digest(node_id: str) -> str:
    """Return the digest portion of a canonical ``blake3:``-prefixed NodeID."""

    if not node_id:
        return ""
    prefix, sep, rest = node_id.partition(":")
    if sep and prefix.lower() == "blake3" and rest:
        return rest
    return node_id


def topic_name(
    asset: str,
    node_type: str,
    node_id: str,
    version: str,
    *,
    dry_run: bool = False,
    existing: Iterable[str] | None = None,
    namespace: object | None = None,
    legacy_code_hash: str | None = None,
) -> str:
    """Return unique topic name per spec.

    The name follows ``{asset}_{node_type}_{short_hash}_{version}{_sim?}`` where
    ``short_hash`` starts from the first eight characters of the NodeID digest
    and grows by two characters until the name is unique within ``existing``.
    """

    digest = _node_id_digest(node_id)
    taken = set(existing or [])
    length = 8
    suffix = "_sim" if dry_run else ""

    if legacy_code_hash:
        legacy_short = legacy_code_hash[:6]
        if legacy_short:
            legacy_base = f"{asset}_{node_type}_{legacy_short}_{version}{suffix}"
            legacy_name = ensure_namespace(legacy_base, namespace)
            if legacy_name in taken:
                return legacy_name

    # First try by growing the short hash up to the full digest length
    while length <= len(digest):
        short_hash = digest[:length]
        base = f"{asset}_{node_type}_{short_hash}_{version}{suffix}"
        name = ensure_namespace(base, namespace)
        if name not in taken:
            return name
        length += 2

    # Fall back to numeric suffix if all hash-length attempts collide
    base = f"{asset}_{node_type}_{digest}_{version}{suffix}"
    base = ensure_namespace(base, namespace)
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


__all__ = [
    "TopicConfig",
    "topic_name",
    "get_config",
    "set_topic_namespace_enabled",
    "topic_namespace_enabled",
    "build_namespace",
    "normalize_namespace",
    "ensure_namespace",
]
