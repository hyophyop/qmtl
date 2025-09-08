import json
import httpx
import pytest

from qmtl.sdk import TagQueryNode
from qmtl.sdk.tagquery_manager import TagQueryManager


class DummyClient:
    def __init__(self, *a, handler=None, **k):
        self._handler = handler
        self._client = httpx.Client(transport=httpx.MockTransport(handler))

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._client.close()

    async def get(self, url, params=None):
        request = httpx.Request("GET", url, params=params)
        resp = self._handler(request)
        resp.request = request
        return resp


@pytest.mark.asyncio
async def test_offline_cache_parity(tmp_path, monkeypatch):
    node_live = TagQueryNode(["t"], interval="60s", period=1)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"queues": [{"queue": "q1", "global": False}]})

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: DummyClient(handler=handler))

    cache = tmp_path / "tagcache.json"
    mgr_live = TagQueryManager("http://gw", cache_path=cache)
    mgr_live.register(node_live)
    await mgr_live.resolve_tags()
    assert node_live.upstreams == ["q1"]

    data = json.loads(cache.read_text())
    assert data["crc32"] == TagQueryManager._compute_crc(data["mappings"])

    node_off = TagQueryNode(["t"], interval="60s", period=1)
    mgr_off = TagQueryManager(cache_path=cache)
    mgr_off.register(node_off)
    await mgr_off.resolve_tags(offline=True)
    assert node_off.upstreams == ["q1"]
    assert node_off.upstreams == node_live.upstreams
