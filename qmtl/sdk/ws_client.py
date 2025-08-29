from __future__ import annotations

import asyncio
import json
import contextlib
from typing import Awaitable, Callable, Optional, TYPE_CHECKING

from urllib.parse import urlparse, urlunparse

import websockets
import logging

if TYPE_CHECKING:  # pragma: no cover - only for typing
    from .node import TagQueryNode


class WebSocketClient:
    """Subscribe to Gateway state updates via WebSocket."""

    def __init__(
        self,
        url: str,
        *,
        on_message: Optional[Callable[[dict], Awaitable[None]]] = None,
        max_retries: int | None = None,
        max_total_time: float | None = None,
        base_delay: float = 1.0,
        backoff_factor: float = 2.0,
        max_delay: float = 8.0,
    ) -> None:
        parts = urlparse(url)
        if parts.path in ("", "/"):
            parts = parts._replace(path="/ws")
            url = urlunparse(parts)
        self.url = url
        self.on_message = on_message
        self.queue_topics: dict[str, str] = {}
        self.sentinel_weights: dict[str, float] = {}
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._ws: websockets.WebSocketClientProtocol | None = None
        self.max_retries = max_retries
        self.max_total_time = max_total_time
        self._base_delay = base_delay
        self._backoff_factor = backoff_factor
        self._max_delay = max_delay

    async def _handle(self, data: dict) -> None:
        event = data.get("event") or data.get("type")
        payload = data.get("data", data)
        if event == "queue_created":
            qid = payload.get("queue_id")
            topic = payload.get("topic")
            if qid and topic:
                self.queue_topics[qid] = topic
        elif event == "queue_update":
            pass  # handled by caller via ``on_message``
        elif event == "sentinel_weight":
            sid = payload.get("sentinel_id")
            weight = payload.get("weight")
            if sid is not None and weight is not None:
                try:
                    self.sentinel_weights[sid] = float(weight)
                except (TypeError, ValueError):
                    logging.warning(
                        "Invalid weight received for sentinel %s: %r", sid, weight
                    )
        if self.on_message:
            await self.on_message(data)

    async def _listen(self) -> None:
        retries = 0
        delay = self._base_delay
        loop = asyncio.get_running_loop()
        start = loop.time()
        while not self._stop_event.is_set():
            try:
                async with websockets.connect(self.url) as ws:
                    self._ws = ws
                    delay = self._base_delay
                    while not self._stop_event.is_set():
                        try:
                            msg = await ws.recv()
                        except websockets.ConnectionClosed:
                            break
                        except Exception:
                            break
                        try:
                            data = json.loads(msg)
                        except json.JSONDecodeError:
                            continue
                        await self._handle(data)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            finally:
                self._ws = None
            if self._stop_event.is_set():
                break
            retries += 1
            if self.max_retries is not None and retries > self.max_retries:
                break
            if self.max_total_time is not None and loop.time() - start > self.max_total_time:
                break
            await asyncio.sleep(delay)
            delay = min(delay * self._backoff_factor, self._max_delay)

    async def start(self) -> None:
        """Start listening in the background."""
        if self._task is None or self._task.done():
            self._stop_event.clear()
            self._task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        """Stop the background listener."""
        self._stop_event.set()
        if self._ws is not None:
            self._ws.close_timeout = 0
            await self._ws.close()
            self._ws = None
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
