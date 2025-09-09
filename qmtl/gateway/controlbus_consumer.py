from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

from qmtl.sdk.node import MatchMode

from .ws import WebSocketHub
from . import metrics as gw_metrics
from .controlbus_codec import decode as decode_cb, PROTO_CONTENT_TYPE

logger = logging.getLogger(__name__)


@dataclass
class ControlBusMessage:
    """Represents a message delivered from the ControlBus."""

    topic: str
    key: str
    etag: str
    run_id: str
    data: dict[str, Any]
    timestamp_ms: Optional[float] = None


class ControlBusConsumer:
    """Consume ControlBus events and relay them to WebSocket clients."""

    def __init__(
        self,
        brokers: list[str] | None,
        topics: list[str],
        group: str,
        *,
        ws_hub: WebSocketHub | None = None,
    ) -> None:
        self.brokers = brokers or []
        self.topics = topics
        self.group = group
        self.ws_hub = ws_hub
        self._queue: asyncio.Queue[ControlBusMessage | None] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._broker_task: asyncio.Task | None = None
        self._consumer: Any | None = None
        self._last_seen: dict[tuple[str, str], tuple[str, str]] = {}
        # Track discovered tag+interval combinations to emit upsert events
        self._known_tag_intervals: set[tuple[tuple[str, ...], int]] = set()

    async def start(self) -> None:
        """Start the background consumer task."""
        if self._task is None:
            self._task = asyncio.create_task(self._worker())
        if self.brokers and self.topics and self._broker_task is None:
            self._broker_task = asyncio.create_task(self._broker_loop())

    async def stop(self) -> None:
        """Stop the background consumer task."""
        if self._broker_task is not None:
            self._broker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._broker_task
            self._broker_task = None
        if self._consumer is not None:
            with contextlib.suppress(Exception):
                await self._consumer.stop()
            self._consumer = None
        await self._queue.put(None)
        if self._task is not None:
            await self._task
            self._task = None

    async def publish(self, message: ControlBusMessage) -> None:
        """Submit a ControlBus message for processing."""
        await self._queue.put(message)

    async def _worker(self) -> None:
        while True:
            msg = await self._queue.get()
            if msg is None:
                break
            try:
                await self._handle_message(msg)
            finally:
                self._queue.task_done()

    async def _broker_ready(self) -> bool:
        """Return ``True`` if brokers are reachable."""
        try:  # pragma: no cover - aiokafka optional
            from aiokafka import AIOKafkaConsumer

            consumer = AIOKafkaConsumer(
                bootstrap_servers=self.brokers,
                group_id=self.group,
                enable_auto_commit=False,
            )
            await consumer.start()
            await consumer.stop()
            return True
        except Exception:
            return False

    async def _wait_for_broker(self, timeout: float = 60.0) -> None:
        """Poll brokers until they become reachable or ``timeout`` expires."""
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            if await self._broker_ready():
                return
            if asyncio.get_running_loop().time() > deadline:
                raise RuntimeError("brokers unavailable")
            await asyncio.sleep(1.0)

    async def _broker_loop(self) -> None:
        try:
            from aiokafka import AIOKafkaConsumer
        except Exception:  # pragma: no cover - dependency optional
            logger.error("aiokafka is required for broker consumption")
            return

        while True:
            try:
                self._consumer = AIOKafkaConsumer(
                    *self.topics,
                    bootstrap_servers=self.brokers,
                    group_id=self.group,
                    enable_auto_commit=False,
                )
                await self._consumer.start()
                while True:
                    msg = await self._consumer.getone()
                    try:
                        cb_msg = self._parse_kafka_message(msg)
                        await self._handle_message(cb_msg)
                        await self._consumer.commit()
                    except Exception as exc:  # pragma: no cover - robustness
                        logger.exception("Error handling ControlBus message: %s", exc)
            except asyncio.CancelledError:
                break
            except Exception as exc:  # pragma: no cover - connection issues
                logger.warning("ControlBus consumer error: %s", exc)
                with contextlib.suppress(Exception):
                    if self._consumer:
                        await self._consumer.stop()
                self._consumer = None
                try:
                    await self._wait_for_broker()
                except Exception:
                    break
            finally:
                if self._consumer is not None:
                    with contextlib.suppress(Exception):
                        await self._consumer.stop()
                    self._consumer = None

    def _parse_kafka_message(self, message: Any) -> ControlBusMessage:
        key = message.key.decode() if message.key else ""
        headers = {k: (v.decode() if isinstance(v, bytes) else v) for k, v in (message.headers or [])}
        etag = headers.get("etag", "")
        run_id = headers.get("run_id", "")
        data: dict[str, Any]
        content_type = headers.get("content_type")
        if content_type == PROTO_CONTENT_TYPE:
            # Placeholder proto path: decode via helper (still JSON today)
            data = decode_cb(message.value if isinstance(message.value, (bytes, bytearray)) else str(message.value).encode())
        else:
            try:
                data = json.loads(message.value.decode()) if isinstance(message.value, (bytes, bytearray)) else json.loads(message.value)
            except Exception:  # pragma: no cover - malformed message
                data = {}
        timestamp_ms = getattr(message, "timestamp", None)
        return ControlBusMessage(
            topic=message.topic,
            key=key,
            etag=etag,
            run_id=run_id,
            data=data,
            timestamp_ms=timestamp_ms,
        )

    async def _handle_message(self, msg: ControlBusMessage) -> None:
        key = (msg.topic, msg.key)
        marker = (msg.etag, msg.run_id)
        if self._last_seen.get(key) == marker:
            gw_metrics.record_event_dropped(msg.topic)
            return
        self._last_seen[key] = marker

        gw_metrics.record_controlbus_message(msg.topic, msg.timestamp_ms)

        if not self.ws_hub:
            return

        if msg.topic == "activation":
            await self.ws_hub.send_activation_updated(msg.data)
        elif msg.topic == "policy":
            await self.ws_hub.send_policy_updated(msg.data)
        elif msg.topic == "queue":
            tags = msg.data.get("tags", [])
            interval = msg.data.get("interval", 0)
            queues = msg.data.get("queues", [])
            match_mode = msg.data.get("match_mode", MatchMode.ANY.value)
            try:
                mode = MatchMode(match_mode)
            except ValueError:
                mode = MatchMode.ANY
            await self.ws_hub.send_queue_update(tags, interval, queues, mode)
            key = (tuple(sorted(tags)), int(interval))
            if key not in self._known_tag_intervals:
                self._known_tag_intervals.add(key)
                await self.ws_hub.send_tagquery_upsert(tags, interval, queues)
        else:
            logger.warning("Unhandled ControlBus topic %s", msg.topic)


__all__ = ["ControlBusConsumer", "ControlBusMessage"]
