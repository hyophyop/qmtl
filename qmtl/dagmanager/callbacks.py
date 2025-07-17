from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx

from ..common import AsyncCircuitBreaker


async def post_with_backoff(
    url: str,
    payload: Any,
    *,
    retries: int = 3,
    base: float = 1.0,
    factor: float = 2.0,
    max_delay: float = 8.0,
    client: Optional[httpx.AsyncClient] = None,
    circuit_breaker: "AsyncCircuitBreaker" | None = None,
) -> httpx.Response:
    """Send HTTP POST with exponential backoff."""
    delay = base
    async with (client if client is not None else httpx.AsyncClient()) as c:
        async def send() -> httpx.Response:
            resp = await c.post(url, json=payload)
            if resp.status_code != 202:
                raise RuntimeError(f"failed with status {resp.status_code}")
            return resp

        wrapped = circuit_breaker(send) if circuit_breaker else send

        for attempt in range(retries):
            try:
                return await wrapped()
            except Exception:
                if attempt < retries - 1:
                    await asyncio.sleep(delay)
                    delay = min(delay * factor, max_delay)
                else:
                    raise

