"""Transport primitives for composing the WorldService client."""
from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Dict, Optional

import httpx

from qmtl.foundation.common import AsyncCircuitBreaker

RetryHook = Callable[[int, Exception], Awaitable[None]]
LatencyObserver = Callable[[float], None]
BreakerCallback = Callable[[AsyncCircuitBreaker], None]


class BreakerRetryTransport:
    """Retrying transport that integrates with an :class:`AsyncCircuitBreaker`."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        breaker: AsyncCircuitBreaker,
        *,
        timeout: float,
        retries: int,
        wait_for_service: Optional[RetryHook] = None,
        observe_latency: Optional[LatencyObserver] = None,
        on_success: Optional[BreakerCallback] = None,
    ) -> None:
        self._client = client
        self._breaker = breaker
        self._timeout = timeout
        self._retries = retries
        self._wait_for_service = wait_for_service
        self._observe_latency = observe_latency
        self._on_success = on_success

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        request_kwargs: Dict[str, Any] = dict(kwargs)
        request_kwargs.setdefault("timeout", self._timeout)

        @self._breaker
        async def _call() -> httpx.Response:
            for attempt in range(self._retries + 1):
                try:
                    start = time.perf_counter()
                    response = await self._client.request(method, url, **request_kwargs)
                    if self._observe_latency is not None:
                        self._observe_latency((time.perf_counter() - start) * 1000)
                    return response
                except Exception as exc:
                    if attempt == self._retries:
                        raise
                    if self._wait_for_service is not None:
                        await self._wait_for_service(attempt + 1, exc)
            raise RuntimeError("retry loop exhausted")

        response = await _call()
        self._breaker.reset()
        if self._on_success is not None:
            self._on_success(self._breaker)
        return response


__all__ = ["BreakerRetryTransport"]
