import httpx
import pytest

from qmtl.dagmanager.callbacks import post


@pytest.mark.asyncio
async def test_post_success(monkeypatch):
    async def mock_post(self, url, json):
        return httpx.Response(202)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    resp = await post("http://gw/cb", {"x": 1})
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_post_failure(monkeypatch):
    async def mock_post(self, url, json):
        return httpx.Response(500)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    with pytest.raises(RuntimeError):
        await post("http://gw/cb", {"x": 1})
