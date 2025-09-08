from __future__ import annotations

"""Standard live data feed interface and WebSocket implementation.

This module exposes a small abstraction usable by strategies or services
that want to consume live updates (prices, signals, control events).
The WebSocketFeed wraps the existing SDK ``WebSocketClient`` with the
same reconnection and heartbeat behavior.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Awaitable, Callable, Optional

from .ws_client import WebSocketClient


class LiveDataFeed(ABC):
    """Abstract live data feed."""

    @abstractmethod
    async def start(self) -> None:  # pragma: no cover - interface
        """Begin streaming in the background."""

    @abstractmethod
    async def stop(self) -> None:  # pragma: no cover - interface
        """Stop streaming and release resources."""


class WebSocketFeed(LiveDataFeed):
    """Live feed backed by the SDK WebSocketClient.

    Parameters
    ----------
    url:
        WebSocket endpoint. If no path is specified, ``/ws`` is assumed.
    on_message:
        Async callback invoked with each parsed JSON message dict.
    token:
        Optional bearer token to attach via ``Authorization`` header.
    max_retries, max_total_time, base_delay, backoff_factor, max_delay:
        Reconnection controls forwarded to ``WebSocketClient``.
    """

    def __init__(
        self,
        url: str,
        *,
        on_message: Optional[Callable[[dict], Awaitable[None]]] = None,
        token: str | None = None,
        max_retries: int | None = None,
        max_total_time: float | None = None,
        base_delay: float = 1.0,
        backoff_factor: float = 2.0,
        max_delay: float = 8.0,
    ) -> None:
        self._client = WebSocketClient(
            url,
            on_message=on_message,
            token=token,
            max_retries=max_retries,
            max_total_time=max_total_time,
            base_delay=base_delay,
            backoff_factor=backoff_factor,
            max_delay=max_delay,
        )
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        await self._client.start()

    async def stop(self) -> None:
        await self._client.stop()


__all__ = ["LiveDataFeed", "WebSocketFeed"]

