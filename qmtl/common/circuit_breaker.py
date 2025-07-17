from __future__ import annotations

"""Asynchronous circuit breaker utility."""

import time
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")


class AsyncCircuitBreaker:
    """Simple circuit breaker for async callables."""

    def __init__(
        self,
        max_failures: int = 3,
        reset_timeout: float = 60.0,
        *,
        on_open: Callable[[], None] | None = None,
        on_close: Callable[[], None] | None = None,
        on_failure: Callable[[int], None] | None = None,
    ) -> None:
        self._max_failures = max_failures
        self._reset_timeout = reset_timeout
        self._on_open = on_open
        self._on_close = on_close
        self._on_failure = on_failure
        self._failures = 0
        self._opened_at: float | None = None

    # --- internal helpers -------------------------------------------------
    def _now(self) -> float:
        return time.monotonic()

    def _maybe_close(self) -> None:
        if self._opened_at is None:
            return
        if self._now() - self._opened_at >= self._reset_timeout:
            self._opened_at = None
            self._failures = 0
            if self._on_close:
                self._on_close()

    # --- public API -------------------------------------------------------
    @property
    def is_open(self) -> bool:
        self._maybe_close()
        return self._opened_at is not None

    @property
    def failures(self) -> int:
        return self._failures

    def __call__(
        self, func: Callable[..., Awaitable[T]]
    ) -> Callable[..., Awaitable[T]]:
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            if self.is_open:
                raise RuntimeError("circuit open")
            try:
                result = await func(*args, **kwargs)
            except Exception:
                self._failures += 1
                if self._on_failure:
                    self._on_failure(self._failures)
                if self._failures >= self._max_failures:
                    if self._opened_at is None:
                        self._opened_at = self._now()
                        if self._on_open:
                            self._on_open()
                raise
            else:
                if self._failures:
                    self._failures = 0
                return result
        return wrapper


__all__ = ["AsyncCircuitBreaker"]
