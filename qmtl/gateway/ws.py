from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from ..common.cloudevents import format_event

import websockets
from websockets.asyncio.server import Server, ServerConnection


logger = logging.getLogger(__name__)


class WebSocketHub:
    """Broadcast Gateway state updates to SDK clients."""

    def __init__(self, host: str = "localhost", port: int = 0) -> None:
        self.host = host
        self.port = port
        self._server: Optional[Server] = None
        self._clients: set[ServerConnection] = set()
        self._lock = asyncio.Lock()
        self._sentinel: object = object()
        self._queue: asyncio.Queue[object] = asyncio.Queue()
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> int:
        """Start the WebSocket server and return the bound port."""
        self._server = await websockets.serve(self._handler, self.host, self.port)
        assert self._server.sockets
        self.port = self._server.sockets[0].getsockname()[1]
        self._task = asyncio.create_task(self._sender_loop())
        return self.port

    async def stop(self) -> None:
        """Stop the server and cleanup resources."""
        await self._queue.put(self._sentinel)
        await self._queue.join()
        self._stop_event.set()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        if self._task:
            await self._task
            self._task = None
        async with self._lock:
            self._clients.clear()

    def is_running(self) -> bool:
        """Return ``True`` if the WebSocket server is active."""
        return self._server is not None

    async def _handler(self, websocket: ServerConnection) -> None:
        async with self._lock:
            self._clients.add(websocket)
        try:
            await websocket.wait_closed()
        finally:
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
                    *(ws.send(msg) for ws in clients), return_exceptions=True
                )
                for client_ws, res in zip(clients, results):
                    if isinstance(res, Exception):
                        logger.warning(
                            "Failed to send message to client %s: %s",
                            client_ws.remote_address,
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
        match_mode: str = "any",
    ) -> None:
        """Broadcast queue update events."""
        event = format_event(
            "qmtl.gateway",
            "queue_update",
            {
                "tags": tags,
                "interval": interval,
                "queues": queues,
                "match_mode": match_mode,
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


__all__ = ["WebSocketHub"]
