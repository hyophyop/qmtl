import asyncio
import httpx
import pytest

from qmtl.dagmanager.callbacks import post_with_backoff
from qmtl.common import AsyncCircuitBreaker


@pytest.mark.asyncio
async def test_post_with_breaker_trips_on_failures(monkeypatch):
    cb = AsyncCircuitBreaker(max_failures=2, reset_timeout=0.1)

    async def mock_post(self, url, json=None):
        return httpx.Response(500)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    async def dummy_sleep(_):
        return None

    monkeypatch.setattr(asyncio, "sleep", dummy_sleep)

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await post_with_backoff(
                "http://x", {}, retries=1, circuit_breaker=cb
            )

    assert cb.is_open
    with pytest.raises(RuntimeError):
        await post_with_backoff("http://x", {}, retries=1, circuit_breaker=cb)
