from __future__ import annotations

"""Asynchronous circuit breaker utility."""

from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")


class AsyncCircuitBreaker:
    """Simple circuit breaker for async callables."""

    def __init__(
        self,
        max_failures: int = 3,
        *,
        on_open: Callable[[], None] | None = None,
        on_close: Callable[[], None] | None = None,
        on_failure: Callable[[int], None] | None = None,
    ) -> None:
        self._max_failures = max_failures
        self._on_open = on_open
        self._on_close = on_close
        self._on_failure = on_failure
        self._failures = 0
        self._is_open = False

    # --- public API -------------------------------------------------------
    @property
    def is_open(self) -> bool:
        return self._is_open

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
                    self.open()
                raise
            else:
                if self._failures:
                    self._failures = 0
                return result
        return wrapper

    # --- manual controls --------------------------------------------------
    def open(self) -> None:
        """Force the circuit open."""
        if not self._is_open:
            self._is_open = True
            if self._on_open:
                self._on_open()

    def close(self) -> None:
        """Close the circuit without resetting failures."""
        if self._is_open:
            self._is_open = False
            if self._on_close:
                self._on_close()

    def reset(self) -> None:
        """Reset failures and close the circuit."""
        self._failures = 0
        self.close()


__all__ = ["AsyncCircuitBreaker"]
