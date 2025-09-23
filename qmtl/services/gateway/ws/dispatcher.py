from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from .connections import ConnectionRegistry, RegisteredClient
from .duplicate import DuplicateTracker
from .filters import FilterEvaluator
from .instrumentation import HubMetrics
from .rate_limit import TokenBucketRateLimiter


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QueuedEvent:
    payload: str
    topic: str | None


class EventDispatcher:
    """Background task that fanouts events to registered clients."""

    def __init__(
        self,
        registry: ConnectionRegistry,
        *,
        metrics: HubMetrics,
        duplicate_tracker: DuplicateTracker,
        filter_evaluator: FilterEvaluator,
        rate_limiter: TokenBucketRateLimiter,
        on_clients_changed: Callable[[], Awaitable[None]],
        queue_maxsize: int = 10000,
    ) -> None:
        self._registry = registry
        self._metrics = metrics
        self._duplicate_tracker = duplicate_tracker
        self._filter_evaluator = filter_evaluator
        self._rate_limiter = rate_limiter
        self._on_clients_changed = on_clients_changed
        self._queue: asyncio.Queue[QueuedEvent | object] = asyncio.Queue(maxsize=queue_maxsize)
        self._sentinel: object = object()
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        await self._queue.put(self._sentinel)
        await self._queue.join()
        await self._task
        self._task = None

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def drain(self) -> None:
        await self._queue.join()

    async def enqueue(self, payload: str, topic: str | None) -> None:
        event = QueuedEvent(payload=payload, topic=topic)
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("event_queue_full_drop", extra={"event": "event_queue_full_drop", "topic": topic})
            if topic is not None:
                with contextlib.suppress(Exception):
                    self._metrics.record_event_dropped(topic)
            with contextlib.suppress(asyncio.QueueEmpty):
                dropped = self._queue.get_nowait()
                self._queue.task_done()
                if dropped is self._sentinel:
                    # Preserve sentinel ordering by requeueing it at the end.
                    self._queue.put_nowait(dropped)
            self._queue.put_nowait(event)

    async def _run(self) -> None:
        while True:
            item = await self._queue.get()
            if item is self._sentinel:
                self._queue.task_done()
                break
            assert isinstance(item, QueuedEvent)
            await self._handle_event(item)
            self._queue.task_done()

    async def _handle_event(self, event: QueuedEvent) -> None:
        decoded = self._filter_evaluator.decode(event.payload)
        envelope = decoded.envelope if decoded.envelope is not None else None
        if self._duplicate_tracker.seen(envelope):
            topic = event.topic or "unknown"
            with contextlib.suppress(Exception):
                self._metrics.record_event_dropped(topic)
            return
        clients = await self._registry.clients_for_topic(event.topic)
        if not clients:
            return
        filtered_clients = self._filter_evaluator.filter_clients(clients, decoded)
        if event.topic is not None:
            with contextlib.suppress(Exception):
                self._metrics.record_event_fanout(event.topic, len(filtered_clients))
        if not filtered_clients:
            return
        await self._fanout(filtered_clients, event.payload)

    async def _fanout(self, clients: list[RegisteredClient], payload: str) -> None:
        async def _send(client: RegisteredClient) -> Any:
            if not self._rate_limiter.allow(client.websocket):
                logger.debug("ws_rate_limited_drop", extra={"event": "ws_rate_limited_drop"})
                return None
            ws = client.websocket
            if hasattr(ws, "send_text"):
                return await ws.send_text(payload)
            if hasattr(ws, "send"):
                return await ws.send(payload)
            raise RuntimeError("Unknown websocket client type")

        results = await asyncio.gather(*(_send(client) for client in clients), return_exceptions=True)
        failures = []
        for client, result in zip(clients, results):
            if isinstance(result, Exception):
                logger.warning(
                    "Failed to send message to client %s: %s",
                    getattr(client.websocket, "client", None) or "unknown",
                    result,
                )
                failures.append(client.websocket)
        if failures:
            removed = await self._registry.remove_many(failures)
            if removed:
                self._rate_limiter.reset_many(removed)
                with contextlib.suppress(Exception):
                    self._metrics.record_ws_drop(len(removed))
                await self._on_clients_changed()
