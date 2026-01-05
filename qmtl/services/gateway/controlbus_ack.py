from __future__ import annotations

"""ControlBus ACK publisher for activation freeze/unfreeze events."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Iterable

from qmtl.foundation.common.cloudevents import format_event
from qmtl.services.kafka import KafkaProducerLike, create_kafka_producer


logger = logging.getLogger(__name__)


class ActivationAckProducer:
    """Publish activation acknowledgements back onto the ControlBus."""

    def __init__(
        self,
        *,
        brokers: Iterable[str] | None = None,
        topic: str = "control.activation.ack",
        required: bool = False,
        retries: int = 2,
        backoff: float = 0.5,
    ) -> None:
        self.brokers = list(brokers or [])
        self.topic = topic
        self._producer: KafkaProducerLike | None = None
        self._required = required
        self._retries = int(retries)
        self._backoff = float(backoff)

    async def start(self) -> None:
        if self._producer is not None:
            return
        if not self.brokers or not self.topic:
            if self._required:
                raise RuntimeError("ControlBus ACK producer requires brokers and topic")
            logger.info("ControlBus ACK producer disabled: missing brokers/topic")
            return
        producer = create_kafka_producer(self.brokers)
        if producer is None:
            if self._required:
                raise RuntimeError("Kafka client unavailable for ControlBus ACKs")
            logger.warning("Kafka client unavailable; ControlBus ACKs disabled")
            return
        self._producer = producer
        await producer.start()

    async def stop(self) -> None:
        producer = self._producer
        if producer is None:
            return
        try:
            await producer.stop()
        except Exception:  # pragma: no cover - best-effort shutdown
            logger.exception("Failed to stop ControlBus ACK producer")
        self._producer = None

    async def publish_ack(
        self,
        *,
        world_id: str,
        run_id: str,
        sequence: int | None,
        phase: str | None,
        etag: str | None,
    ) -> None:
        producer = self._producer
        if producer is None:
            return
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        payload = {
            "type": "ActivationAck",
            "version": 1,
            "world_id": world_id,
            "run_id": run_id,
            "sequence": sequence,
            "phase": phase,
            "etag": etag,
            "ts": now,
            "ack_ts": now,
            "idempotency_key": f"activation_ack:{world_id}:{run_id}:{sequence or 0}:{phase or 'unknown'}:1",
        }
        corr = f"activation:{world_id}:{run_id}"
        event = format_event(
            "qmtl.services.gateway",
            "activation_ack",
            payload,
            correlation_id=corr,
        )
        data = json.dumps(event).encode()
        key = (world_id or "").encode() or b""
        last_exc: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                await producer.send_and_wait(self.topic, data, key=key)
                return
            except Exception as exc:  # pragma: no cover - best-effort reliability
                last_exc = exc
                if attempt >= self._retries:
                    break
                await asyncio.sleep(self._backoff * (attempt + 1))
        if last_exc:
            raise last_exc


__all__ = ["ActivationAckProducer"]
