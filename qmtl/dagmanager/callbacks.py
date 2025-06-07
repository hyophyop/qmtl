from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx


async def post_with_backoff(
    url: str,
    payload: Any,
    *,
    retries: int = 3,
    base: float = 1.0,
    factor: float = 2.0,
    max_delay: float = 8.0,
    client: Optional[httpx.AsyncClient] = None,
) -> httpx.Response:
    """Send HTTP POST with exponential backoff."""
    delay = base
    async with (client or httpx.AsyncClient()) as c:
        for attempt in range(retries):
            resp = await c.post(url, json=payload)
            if resp.status_code == 202:
                return resp
            if attempt < retries - 1:
                await asyncio.sleep(delay)
                delay = min(delay * factor, max_delay)
        resp.raise_for_status()
        return resp
