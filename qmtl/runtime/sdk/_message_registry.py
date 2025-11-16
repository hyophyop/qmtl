from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


class AsyncMessageRegistry:
    """Dispatch async message handlers by event name."""

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[dict[str, Any]], Awaitable[None]]] = {}

    def register(
        self, event: str, handler: Callable[[dict[str, Any]], Awaitable[None]]
    ) -> None:
        self._handlers[event] = handler

    async def dispatch(self, event: str | None, payload: dict[str, Any]) -> bool:
        handler = self._handlers.get(event or "")
        if handler is None:
            return False
        await handler(payload)
        return True
