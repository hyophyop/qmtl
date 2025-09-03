from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional
import asyncio

from .diff_service import NodeRepository
from .kafka_admin import KafkaAdmin
from .controlbus_producer import ControlBusProducer


@dataclass
class QueueCompletionMonitor:
    """Detect inactive queues and emit events when completed."""

    repo: NodeRepository
    admin: KafkaAdmin
    bus: ControlBusProducer | None = None
    interval: float = 5.0
    threshold: int = 2
    _sizes: Dict[str, int] = field(default_factory=dict)
    _stalled: Dict[str, int] = field(default_factory=dict)
    _completed: set[str] = field(default_factory=set)
    _task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            finally:
                self._task = None

    async def _run(self) -> None:
        try:
            while True:
                await self.check_once()
                await asyncio.sleep(self.interval)
        except asyncio.CancelledError:  # pragma: no cover - background task
            pass

    async def check_once(self) -> None:
        sizes = self.admin.get_topic_sizes()
        for topic, size in sizes.items():
            prev = self._sizes.get(topic)
            if prev is not None and size == prev:
                self._stalled[topic] = self._stalled.get(topic, 0) + 1
            else:
                self._stalled[topic] = 0
            self._sizes[topic] = size
            if (
                self._stalled[topic] >= self.threshold
                and topic not in self._completed
            ):
                record = self.repo.get_node_by_queue(topic)
                if record and record.interval is not None and record.tags:
                    payload = {
                        "tags": list(record.tags),
                        "interval": record.interval,
                        "queues": [],
                        "match_mode": "any",
                    }
                    if self.bus:
                        await self.bus.publish_queue_update(
                            payload["tags"],
                            payload["interval"],
                            payload["queues"],
                            payload["match_mode"],
                        )
                    self._completed.add(topic)


__all__ = ["QueueCompletionMonitor"]
