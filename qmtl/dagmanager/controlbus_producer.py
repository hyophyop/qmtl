from __future__ import annotations

import contextlib
import json
from typing import Any, Iterable

from qmtl.common.cloudevents import EVENT_SCHEMA_VERSION


class ControlBusProducer:
    """Publish control events to the internal bus (e.g. Kafka)."""

    def __init__(self, *, brokers: Iterable[str] | None = None, topic: str = "queue", producer: Any | None = None) -> None:
        self.brokers = list(brokers or [])
        self.topic = topic
        self._producer = producer

    async def start(self) -> None:
        if self._producer is not None or not self.brokers:
            return
        try:  # pragma: no cover - optional dependency
            from aiokafka import AIOKafkaProducer
        except Exception:
            return
        self._producer = AIOKafkaProducer(bootstrap_servers=self.brokers)
        await self._producer.start()

    async def stop(self) -> None:
        if self._producer is None:
            return
        with contextlib.suppress(Exception):  # pragma: no cover - best effort
            await self._producer.stop()
        self._producer = None

    async def publish_queue_update(self, tags, interval, queues, match_mode: str = "any") -> None:
        if self._producer is None:
            return
        payload = {
            "tags": list(tags),
            "interval": interval,
            "queues": list(queues),
            "match_mode": match_mode,
            "version": EVENT_SCHEMA_VERSION,
        }
        data = json.dumps(payload).encode()
        key = ",".join(tags).encode()
        await self._producer.send_and_wait(self.topic, data, key=key)


__all__ = ["ControlBusProducer"]
