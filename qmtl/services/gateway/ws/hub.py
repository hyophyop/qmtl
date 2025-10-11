from __future__ import annotations

import contextlib
import json
import logging
from typing import Any, Optional, Set

from fastapi import WebSocket

from qmtl.foundation.common.tagquery import MatchMode

from qmtl.foundation.common.cloudevents import format_event
from .connections import ConnectionRegistry
from .dispatcher import EventDispatcher
from .duplicate import DuplicateTracker
from .filters import FilterEvaluator
from .instrumentation import HubMetrics
from .rate_limit import TokenBucketRateLimiter
from .server import ServerManager


logger = logging.getLogger(__name__)


class WebSocketHub:
    """Broadcast Gateway state updates to SDK clients."""

    def __init__(
        self,
        *,
        metrics: HubMetrics | None = None,
        queue_maxsize: int = 10000,
        duplicate_window: int = 10000,
        rate_limit_per_sec: int | None = None,
    ) -> None:
        self._metrics = metrics or HubMetrics.default()
        self._registry = ConnectionRegistry()
        self._duplicate_tracker = DuplicateTracker(window=duplicate_window)
        self._filter_evaluator = FilterEvaluator()
        self._rate_limiter = TokenBucketRateLimiter()
        self._configure_rate_limit(rate_limit_per_sec)
        self._dispatcher = EventDispatcher(
            self._registry,
            metrics=self._metrics,
            duplicate_tracker=self._duplicate_tracker,
            filter_evaluator=self._filter_evaluator,
            rate_limiter=self._rate_limiter,
            on_clients_changed=self._update_subscriber_metrics,
            queue_maxsize=queue_maxsize,
        )
        self._server = ServerManager(
            self._registry,
            on_client_join=self._on_server_join,
            on_client_leave=self._on_server_leave,
        )
        self._seq_no: int = 0

    async def start(self, *, start_server: bool = False) -> int:
        await self._dispatcher.start()
        return await self._server.ensure_running(start_server=start_server)

    async def stop(self) -> None:
        await self._dispatcher.stop()
        await self._server.stop()
        clients = await self._registry.clear()
        for ws in clients:
            with contextlib.suppress(Exception):
                await ws.close()
        self._rate_limiter.clear()
        self._duplicate_tracker.clear()

    def is_running(self) -> bool:
        return self._dispatcher.is_running()

    async def drain(self) -> None:
        await self._dispatcher.drain()

    async def connect(self, websocket: WebSocket, topics: Optional[Set[str]] = None) -> None:
        await websocket.accept()
        await self._registry.add(websocket, topics=topics)
        await self._update_subscriber_metrics()

    async def disconnect(self, websocket: WebSocket) -> None:
        removed = await self._registry.remove(websocket)
        self._rate_limiter.reset(websocket)
        if removed:
            with contextlib.suppress(Exception):
                self._metrics.record_ws_drop(1)
            await self._update_subscriber_metrics()

    async def set_topics(self, websocket: WebSocket, topics: Optional[Set[str]]) -> None:
        await self._registry.update_topics(websocket, topics)
        await self._update_subscriber_metrics()

    async def set_filters(
        self,
        websocket: Any,
        *,
        world_id: str | None = None,
        strategy_id: str | None = None,
        scopes: Set[str] | None = None,
    ) -> None:
        await self._registry.update_filters(
            websocket,
            world_id=world_id,
            strategy_id=strategy_id,
            scopes=scopes,
        )

    async def broadcast(self, data: dict, *, topic: Optional[str] = None) -> None:
        if "seq_no" not in data:
            with contextlib.suppress(Exception):
                self._seq_no += 1
                data["seq_no"] = self._seq_no
        payload = json.dumps(data)
        await self._dispatcher.enqueue(payload, topic)
        if topic is not None:
            is_new = await self._registry.note_topic(topic)
            if is_new:
                await self._update_subscriber_metrics()

    async def _update_subscriber_metrics(self) -> None:
        counts = await self._registry.topic_counts()
        with contextlib.suppress(Exception):
            self._metrics.update_ws_subscribers(counts)

    async def _on_server_join(self, websocket: Any) -> None:
        await self._update_subscriber_metrics()

    async def _on_server_leave(self, websocket: Any) -> None:
        self._rate_limiter.reset(websocket)
        with contextlib.suppress(Exception):
            self._metrics.record_ws_drop(1)
        await self._update_subscriber_metrics()

    async def _send_event(self, event_type: str, payload: dict, *, topic: str | None = None) -> None:
        event = format_event("qmtl.services.gateway", event_type, payload)
        await self.broadcast(event, topic=topic)

    async def send_progress(self, strategy_id: str, status: str) -> None:
        payload = {"strategy_id": strategy_id, "status": status, "version": 1}
        await self._send_event("progress", payload)

    async def send_queue_map(
        self,
        strategy_id: str,
        queue_map: dict[str, list[str] | str],
    ) -> None:
        payload = {"strategy_id": strategy_id, "queue_map": queue_map, "version": 1}
        await self._send_event("queue_map", payload)

    async def send_queue_update(
        self,
        tags: list[str],
        interval: int,
        queues: list[dict[str, object]],
        match_mode: MatchMode = MatchMode.ANY,
        *,
        world_id: str | None = None,
        etag: str | None = None,
        ts: str | None = None,
    ) -> None:
        payload = {
            "tags": tags,
            "interval": interval,
            "queues": queues,
            "match_mode": match_mode.value,
            **({"world_id": world_id} if world_id else {}),
            **({"etag": etag} if etag is not None else {}),
            **({"ts": ts} if ts is not None else {}),
            "version": 1,
        }
        await self._send_event("queue_update", payload, topic="queue")

    async def send_tagquery_upsert(
        self, tags: list[str], interval: int, queues: list[dict[str, object]]
    ) -> None:
        payload = {"tags": tags, "interval": interval, "queues": queues, "version": 1}
        await self._send_event("tagquery.upsert", payload, topic="queue")

    async def send_sentinel_weight(self, sentinel_id: str, weight: float) -> None:
        payload = {"sentinel_id": sentinel_id, "weight": weight, "version": 1}
        await self._send_event("sentinel_weight", payload, topic="activation")

    async def send_activation_updated(self, payload: dict) -> None:
        payload.setdefault("version", 1)
        await self._send_event("activation_updated", payload, topic="activation")

    async def send_policy_updated(self, payload: dict) -> None:
        payload.setdefault("version", 1)
        await self._send_event("policy_updated", payload, topic="policy")

    async def send_deprecation_notice(self, payload: dict) -> None:
        payload.setdefault("version", 1)
        await self._send_event("deprecation.notice", payload, topic="deprecation")

    def _configure_rate_limit(self, explicit_rate: int | None) -> None:
        if explicit_rate is None:
            self._rate_limiter.configure(0)
            return
        rate = max(0, int(explicit_rate))
        if rate != explicit_rate:
            logger.warning(
                "WebSocket rate limit must be non-negative; clamped value to %s",
                rate,
            )
        self._rate_limiter.configure(rate)
