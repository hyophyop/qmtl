from __future__ import annotations

import asyncio
import json
from typing import Optional

import websockets
from websockets.server import WebSocketServerProtocol


class WebSocketHub:
    """Broadcast Gateway state updates to SDK clients."""

    def __init__(self, host: str = "localhost", port: int = 0) -> None:
        self.host = host
        self.port = port
        self._server: Optional[websockets.server.Serve] = None
        self._clients: set[WebSocketServerProtocol] = set()
        self._lock = asyncio.Lock()
        self._queue: asyncio.Queue[str] = asyncio.Queue()
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

    async def _handler(self, websocket: WebSocketServerProtocol) -> None:
        async with self._lock:
            self._clients.add(websocket)
        try:
            await websocket.wait_closed()
        finally:
            async with self._lock:
                self._clients.discard(websocket)

    async def _sender_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                msg = await asyncio.wait_for(self._queue.get(), 0.1)
            except asyncio.TimeoutError:
                continue
            async with self._lock:
                clients = list(self._clients)
            if clients:
                await asyncio.gather(*(ws.send(msg) for ws in clients), return_exceptions=True)
            self._queue.task_done()

    async def broadcast(self, data: dict) -> None:
        """Queue ``data`` for broadcast to all connected clients."""
        await self._queue.put(json.dumps(data))

    async def send_progress(self, strategy_id: str, status: str) -> None:
        await self.broadcast({"event": "progress", "strategy_id": strategy_id, "status": status})

    async def send_queue_map(self, strategy_id: str, queue_map: dict[str, list[str] | str]) -> None:
        await self.broadcast({"event": "queue_map", "strategy_id": strategy_id, "queue_map": queue_map})


__all__ = ["WebSocketHub"]
