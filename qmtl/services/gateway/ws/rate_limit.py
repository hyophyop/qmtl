from __future__ import annotations

import asyncio
from typing import Any, Callable


class TokenBucketRateLimiter:
    """Simple per-client token bucket rate limiter."""

    def __init__(self, rate_per_sec: int = 0, *, time_source: Callable[[], float] | None = None) -> None:
        self._rate = max(0, rate_per_sec)
        self._time_source = time_source or self._default_time
        self._state: dict[Any, tuple[float, float]] = {}

    def configure(self, rate_per_sec: int) -> None:
        self._rate = max(0, rate_per_sec)
        if self._rate == 0:
            self._state.clear()

    def allow(self, client: Any, *, now: float | None = None) -> bool:
        if self._rate <= 0:
            return True
        current = now if now is not None else self._time_source()
        capacity = float(self._rate)
        tokens, last = self._state.get(client, (capacity, current))
        elapsed = max(0.0, current - last)
        tokens = min(capacity, tokens + elapsed * self._rate)
        if tokens < 1.0:
            self._state[client] = (tokens, current)
            return False
        tokens -= 1.0
        self._state[client] = (tokens, current)
        return True

    def reset(self, client: Any) -> None:
        self._state.pop(client, None)

    def reset_many(self, clients: list[Any]) -> None:
        for client in clients:
            self._state.pop(client, None)

    def clear(self) -> None:
        self._state.clear()

    @staticmethod
    def _default_time() -> float:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        return loop.time()
