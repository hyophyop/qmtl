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

    grouped: dict[tuple[str, int], set[str]] = defaultdict(set)
    for info in queues:
        if not info.tag:
            continue
        if info.interval is None:
            continue
        try:
            interval = int(info.interval)
        except (TypeError, ValueError):
            LOGGER.debug("Skipping queue %s with non-integer interval %r", info.name, info.interval)
            continue
        grouped[(info.tag, interval)].add(info.name)

    for (tag, interval), _dropped in grouped.items():
        current: list[str] = []
        if repo is not None:
            try:
                records = repo.get_queues_by_tag([tag], interval, match_mode=match_mode)
            except Exception as exc:  # pragma: no cover - defensive logging
                LOGGER.warning(
                    "Failed to resolve remaining queues for tag=%s interval=%s: %s",
                    tag,
                    interval,
                    exc,
                )
            else:
                current = [
                    str(entry.get("queue"))
                    for entry in records
                    if isinstance(entry, Mapping) and entry.get("queue")
                ]
        await bus.publish_queue_update([tag], interval, current, match_mode)


__all__ = ["publish_queue_updates"]
