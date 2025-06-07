from __future__ import annotations

import asyncio
import json
from typing import Awaitable, Callable, Optional

import websockets


class WebSocketClient:
    """Subscribe to Gateway state updates via WebSocket."""

    def __init__(
        self,
        url: str,
        *,
        on_message: Optional[Callable[[dict], Awaitable[None]]] = None,
    ) -> None:
        self.url = url
        self.on_message = on_message
        self.queue_topics: dict[str, str] = {}
        self.sentinel_weights: dict[str, float] = {}
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def _handle(self, data: dict) -> None:
        event = data.get("event")
        if event == "queue_created":
            qid = data.get("queue_id")
            topic = data.get("topic")
            if qid and topic:
                self.queue_topics[qid] = topic
        elif event == "sentinel_weight":
            sid = data.get("sentinel_id")
            weight = data.get("weight")
            if sid is not None and weight is not None:
                try:
                    self.sentinel_weights[sid] = float(weight)
                except (TypeError, ValueError):
                    pass
        if self.on_message:
            await self.on_message(data)

    async def _listen(self) -> None:
        async with websockets.connect(self.url) as ws:
            while not self._stop_event.is_set():
                try:
                    msg = await ws.recv()
                except websockets.ConnectionClosed:
                    # Expected closure, break the loop
                    break
                except Exception as e:
                    # Log unexpected errors and decide how to handle (e.g., log and break, log and continue, attempt reconnect)
                    # logging.error(f"Unexpected error during WebSocket receive: {e}")
                    break # Or continue, or implement retry logic
                try:
                    data = json.loads(msg)
                except json.JSONDecodeError:
                    continue
                await self._handle(data)

    async def start(self) -> None:
        """Start listening in the background."""
        if self._task is None or self._task.done():
            self._stop_event.clear()
            self._task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        """Stop the background listener."""
        self._stop_event.set()
        if self._task is not None:
            await self._task
            self._task = None
