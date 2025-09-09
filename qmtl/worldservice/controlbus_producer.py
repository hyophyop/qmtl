from __future__ import annotations

import contextlib
import json
from typing import Any, Dict, Iterable


class ControlBusProducer:
    """Publish updates to the internal ControlBus."""

    def __init__(self, *, brokers: Iterable[str] | None = None, topic: str = "policy", producer: Any | None = None) -> None:
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

    async def publish_policy_update(self, world_id: str, strategies: Iterable[str], *, version: int = 1) -> None:
        if self._producer is None:
            return
        payload: Dict[str, Any] = {
            "type": "PolicyUpdated",
            "world_id": world_id,
            "strategies": list(strategies),
            "version": version,
        }
        data = json.dumps(payload).encode()
        key = world_id.encode()
        await self._producer.send_and_wait(self.topic, data, key=key)

    async def publish_activation_update(self, world_id: str, payload: Dict[str, Any], *, version: int = 1) -> None:
        if self._producer is None:
            return
        evt: Dict[str, Any] = {
            "type": "ActivationUpdated",
            "world_id": world_id,
            **payload,
            "version": version,
        }
        data = json.dumps(evt).encode()
        key = world_id.encode()
        await self._producer.send_and_wait(self.topic, data, key=key)


__all__ = ["ControlBusProducer"]
