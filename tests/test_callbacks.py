import asyncio

import httpx
import pytest

from qmtl.dagmanager.callbacks import post_with_backoff


@pytest.mark.asyncio
async def test_post_with_backoff(monkeypatch):
    calls = []

    async def mock_post(self, url, json):
        calls.append(json)
        status = 500 if len(calls) < 2 else 202
        return httpx.Response(status)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    async def dummy_sleep(_):
        return None

    monkeypatch.setattr(asyncio, "sleep", dummy_sleep)

    resp = await post_with_backoff("http://gw/cb", {"x": 1})
    assert resp.status_code == 202
    assert len(calls) == 2
