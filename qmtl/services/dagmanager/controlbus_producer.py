from __future__ import annotations

import contextlib
import json
import logging
from datetime import datetime, timezone
from typing import Iterable

from qmtl.services.kafka import KafkaProducerLike, create_kafka_producer


class ControlBusProducer:
    """Publish control events to the internal bus (e.g. Kafka)."""

    def __init__(
        self,
        *,
        brokers: Iterable[str] | None = None,
        topic: str = "queue",
        sentinel_topic: str = "sentinel_weight",
        producer: KafkaProducerLike | None = None,
        required: bool = False,
        logger: logging.Logger | None = None,
    ) -> None:
        self.brokers = list(brokers or [])
        self.topic = topic
        self.sentinel_topic = sentinel_topic
        self._producer: KafkaProducerLike | None = producer
        self._required = required
        self._logger = logger or logging.getLogger(__name__)

    async def start(self) -> None:
        if self._producer is not None:
            return
        if not self.brokers or not self.topic or not self.sentinel_topic:
            self._handle_disabled("brokers/topics not configured")
            return
        producer = create_kafka_producer(self.brokers)
        if producer is None:
            self._handle_disabled("Kafka client not available for ControlBus")
            return
        self._producer = producer
        await producer.start()

    async def stop(self) -> None:
        producer = self._producer
        if producer is None:
            return
        with contextlib.suppress(Exception):  # pragma: no cover - best effort
            await producer.stop()
        self._producer = None

    async def publish_queue_update(self, tags, interval, queues, match_mode: str = "any", *, version: int = 1) -> None:
        producer = self._producer
        if producer is None:
            return
        tags_list = list(tags)
        tags_hash = ".".join(sorted(tags_list))
        etag = f"q:{tags_hash}:{interval}:{version}"
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        payload = {
            "type": "QueueUpdated",
            "tags": tags_list,
            "interval": interval,
            "queues": list(queues),
            "match_mode": match_mode,
            "version": version,
            "etag": etag,
            "ts": ts,
        }
        data = json.dumps(payload).encode()
        key = ",".join(tags_list).encode()
        await producer.send_and_wait(self.topic, data, key=key)

    async def publish_sentinel_weight(
        self,
        sentinel_id: str,
        weight: float,
        *,
        sentinel_version: str | None = None,
        world_id: str | None = None,
        version: int = 1,
    ) -> None:
        """Publish a sentinel weight control event."""

        producer = self._producer
        if producer is None:
            return

        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        weight_value = float(weight)
        if weight_value < 0.0:
            weight_value = 0.0
        elif weight_value > 1.0:
            weight_value = 1.0
        weight_str = f"{weight_value:.6f}"
        version_label = sentinel_version or ""
        etag = f"sw:{sentinel_id}:{version_label}:{weight_str}:{version}"
        payload = {
            "type": "SentinelWeightUpdated",
            "sentinel_id": sentinel_id,
            "weight": weight_value,
            "version": version,
            "etag": etag,
            "ts": ts,
        }
        if version_label:
            payload["sentinel_version"] = version_label
        if world_id:
            payload["world_id"] = world_id
        data = json.dumps(payload).encode()
        key = sentinel_id.encode()
        await producer.send_and_wait(self.sentinel_topic, data, key=key)

    def _handle_disabled(self, reason: str) -> None:
        if self._required:
            raise RuntimeError(f"ControlBus unavailable: {reason}")
        self._logger.warning("ControlBus disabled: %s", reason)


__all__ = ["ControlBusProducer"]
