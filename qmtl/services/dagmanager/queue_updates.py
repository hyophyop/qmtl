"""Utilities for emitting ControlBus queue update events."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Iterable, Mapping

from .controlbus_producer import ControlBusProducer
from .garbage_collector import QueueInfo
from .repository import NodeRepository

LOGGER = logging.getLogger(__name__)


async def publish_queue_updates(
    bus: ControlBusProducer,
    queues: Iterable[QueueInfo],
    *,
    repo: NodeRepository | None = None,
    match_mode: str = "any",
) -> None:
    """Publish ControlBus updates for processed queues.

    The helper groups ``queues`` by ``(tag, interval)`` and looks up the
    remaining queues for the same group via ``repo`` when available so that
    subscribers observe the post-GC view.
    """

    grouped = _group_by_tag_interval(queues)

    for (tag, interval), _dropped in grouped.items():
        current = _resolve_remaining(repo, tag, interval, match_mode)
        await bus.publish_queue_update([tag], interval, current, match_mode)


def _group_by_tag_interval(queues: Iterable[QueueInfo]) -> dict[tuple[str, int], set[str]]:
    grouped: dict[tuple[str, int], set[str]] = defaultdict(set)
    for info in queues:
        if not info.tag or info.interval is None:
            continue
        interval = _coerce_interval(info)
        if interval is None:
            continue
        grouped[(info.tag, interval)].add(info.name)
    return grouped


def _coerce_interval(info: QueueInfo) -> int | None:
    try:
        return int(info.interval) if info.interval is not None else None
    except (TypeError, ValueError):
        LOGGER.debug("Skipping queue %s with non-integer interval %r", info.name, info.interval)
        return None


def _resolve_remaining(
    repo: NodeRepository | None, tag: str, interval: int, match_mode: str
) -> list[Mapping[str, object]]:
    if repo is None:
        return []
    try:
        records = repo.get_queues_by_tag([tag], interval, match_mode=match_mode)
    except Exception as exc:  # pragma: no cover - defensive logging
        LOGGER.warning(
            "Failed to resolve remaining queues for tag=%s interval=%s: %s",
            tag,
            interval,
            exc,
        )
        return []

    return [
        dict(entry) if not isinstance(entry, dict) else entry
        for entry in records
        if isinstance(entry, Mapping) and entry.get("queue")
    ]


__all__ = ["publish_queue_updates"]
