from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Optional, Set

from fastapi import WebSocket

from qmtl.sdk.node import MatchMode

from ..common.cloudevents import format_event


logger = logging.getLogger(__name__)


class WebSocketHub:
    """Broadcast Gateway state updates to SDK clients."""

    def __init__(self) -> None:
        self._clients: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._sentinel: object = object()
        self._queue: asyncio.Queue[object] = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the internal sender loop."""
        if self._task is None:
            self._task = asyncio.create_task(self._sender_loop())

    async def stop(self) -> None:
        """Stop the sender loop and disconnect clients."""
        await self._queue.put(self._sentinel)
        await self._queue.join()
        if self._task:
            await self._task
            self._task = None
        async with self._lock:
            for ws in list(self._clients):
                with contextlib.suppress(Exception):
                    await ws.close()
            self._clients.clear()

    def is_running(self) -> bool:
        """Return ``True`` if the sender loop is active."""
        return self._task is not None and not self._task.done()

    async def connect(self, websocket: WebSocket) -> None:
        """Register an incoming WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self._clients.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            self._clients.discard(websocket)

    async def _sender_loop(self) -> None:
        while True:
            msg = await self._queue.get()
            if msg is self._sentinel:
                self._queue.task_done()
                break
            async with self._lock:
                clients = list(self._clients)
            if clients:
                results = await asyncio.gather(
                    *(ws.send_text(msg) for ws in clients), return_exceptions=True
                )
                for client_ws, res in zip(clients, results):
                    if isinstance(res, Exception):
                        logger.warning(
                            "Failed to send message to client %s: %s",
                            getattr(client_ws, "client", None) or "unknown",
                            res,
                        )
            self._queue.task_done()

    async def broadcast(self, data: dict) -> None:
        """Queue ``data`` for broadcast to all connected clients."""
        await self._queue.put(json.dumps(data))

    async def send_progress(self, strategy_id: str, status: str) -> None:
        event = format_event(
            "qmtl.gateway",
            "progress",
            {"strategy_id": strategy_id, "status": status},
        )
        await self.broadcast(event)

    async def send_queue_map(
        self, strategy_id: str, queue_map: dict[str, list[str] | str]
    ) -> None:
        event = format_event(
            "qmtl.gateway",
            "queue_map",
            {"strategy_id": strategy_id, "queue_map": queue_map},
        )
        await self.broadcast(event)

    async def send_queue_update(
        self,
        tags: list[str],
        interval: int,
        queues: list[str],
        match_mode: MatchMode = MatchMode.ANY,
    ) -> None:
        """Broadcast queue update events.

        ``match_mode`` must be ``MatchMode.ANY`` or ``MatchMode.ALL``.
        """
        event = format_event(
            "qmtl.gateway",
            "queue_update",
            {
                "tags": tags,
                "interval": interval,
                "queues": queues,
                "match_mode": match_mode.value,
            },
        )
        await self.broadcast(event)

    async def send_sentinel_weight(self, sentinel_id: str, weight: float) -> None:
        """Broadcast sentinel weight updates."""
        event = format_event(
            "qmtl.gateway",
            "sentinel_weight",
            {"sentinel_id": sentinel_id, "weight": weight},
        )
        await self.broadcast(event)

    async def send_activation_updated(self, payload: dict) -> None:
        """Broadcast activation updates."""
        event = format_event("qmtl.gateway", "activation_updated", payload)
        await self.broadcast(event)

    async def send_policy_updated(self, payload: dict) -> None:
        """Broadcast policy updates."""
        event = format_event("qmtl.gateway", "policy_updated", payload)
        await self.broadcast(event)


__all__ = ["WebSocketHub"]
