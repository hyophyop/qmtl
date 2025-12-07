from __future__ import annotations

"""ControlBus ACK publisher for activation freeze/unfreeze events."""

import json
import logging
from datetime import datetime, timezone
from typing import Iterable

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
    ) -> None:
        self.brokers = list(brokers or [])
        self.topic = topic
        self._producer: KafkaProducerLike | None = None
        self._required = required

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
            "ack_ts": now,
        }
        data = json.dumps(payload).encode()
        key = (world_id or "").encode() or b""
        await producer.send_and_wait(self.topic, data, key=key)


__all__ = ["ActivationAckProducer"]
