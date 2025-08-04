from __future__ import annotations

from typing import Any, Optional

import httpx

from ..common import AsyncCircuitBreaker


async def post(
    url: str,
    payload: Any,
    *,
    client: Optional[httpx.AsyncClient] = None,
    circuit_breaker: "AsyncCircuitBreaker" | None = None,
) -> httpx.Response:
    """Send a single HTTP POST and raise on non-202 responses."""
    async with (client if client is not None else httpx.AsyncClient()) as c:
        async def send() -> httpx.Response:
            resp = await c.post(url, json=payload)
            if resp.status_code != 202:
                raise RuntimeError(f"failed with status {resp.status_code}")
            return resp

        wrapped = circuit_breaker(send) if circuit_breaker else send
        return await wrapped()

