from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from prometheus_client import Gauge

from qmtl.sdk.node import MatchMode

from .ws import WebSocketHub

logger = logging.getLogger(__name__)


# Metrics for monitoring consumer delay and clock skew
_controlbus_lag_ms = Gauge(
    "controlbus_lag_ms",
    "Delay between event creation and processing in milliseconds",
    ["topic"],
)
_controlbus_skew_ms = Gauge(
    "controlbus_skew_ms",
    "Clock skew between event timestamp and consumer processing time in milliseconds",
    ["topic"],
)


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
        self._last_seen: dict[tuple[str, str], tuple[str, str]] = {}

    async def start(self) -> None:
        """Start the background consumer task."""
        if self._task is None:
            self._task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        """Stop the background consumer task."""
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

    async def _handle_message(self, msg: ControlBusMessage) -> None:
        key = (msg.topic, msg.key)
        marker = (msg.etag, msg.run_id)
        if self._last_seen.get(key) == marker:
            return
        self._last_seen[key] = marker

        now_ms = time.time() * 1000
        if msg.timestamp_ms is not None:
            lag = max(0.0, now_ms - msg.timestamp_ms)
            _controlbus_lag_ms.labels(topic=msg.topic).set(lag)
            _controlbus_skew_ms.labels(topic=msg.topic).set(msg.timestamp_ms - now_ms)

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
        else:
            logger.warning("Unhandled ControlBus topic %s", msg.topic)


__all__ = ["ControlBusConsumer", "ControlBusMessage"]
