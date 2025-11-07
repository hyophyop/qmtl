from __future__ import annotations

import contextlib
import json
from typing import Any, Dict, Iterable

from qmtl.foundation.common.cloudevents import format_event


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

    async def _publish(self, event_type: str, world_id: str, payload: Dict[str, Any]) -> None:
        if self._producer is None:
            return
        event = format_event("qmtl.services.worldservice", event_type, payload)
        data = json.dumps(event).encode()
        key = world_id.encode()
        await self._producer.send_and_wait(self.topic, data, key=key)

    async def publish_policy_update(
        self,
        world_id: str,
        policy_version: int,
        checksum: str,
        status: str,
        ts: str,
        *,
        version: int = 1,
    ) -> None:
        payload: Dict[str, Any] = {
            "world_id": world_id,
            "policy_version": policy_version,
            "checksum": checksum,
            "status": status,
            "ts": ts,
            "version": version,
        }
        await self._publish("policy_updated", world_id, payload)

    async def publish_activation_update(
        self,
        world_id: str,
        *,
        etag: str,
        run_id: str,
        ts: str,
        state_hash: str,
        payload: Dict[str, Any] | None = None,
        version: int = 1,
        requires_ack: bool = False,
        sequence: int | None = None,
    ) -> None:
        body: Dict[str, Any] = {
            "world_id": world_id,
            "etag": etag,
            "run_id": run_id,
            "ts": ts,
            "state_hash": state_hash,
            "version": version,
        }
        if payload:
            body.update(payload)
        if requires_ack:
            body["requires_ack"] = True
        if sequence is not None:
            body["sequence"] = sequence
        await self._publish("activation_updated", world_id, body)

    async def publish_rebalancing_plan(
        self,
        world_id: str,
        plan: Dict[str, Any],
        *,
        version: int = 1,
    ) -> None:
        payload: Dict[str, Any] = {
            "world_id": world_id,
            "plan": plan,
            "version": version,
        }
        await self._publish("rebalancing_planned", world_id, payload)


__all__ = ["ControlBusProducer"]
