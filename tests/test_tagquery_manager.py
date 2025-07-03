import asyncio
import httpx
import pytest

from qmtl.sdk import TagQueryNode
from qmtl.sdk.tagquery_manager import TagQueryManager


@pytest.mark.asyncio
async def test_resolve_and_update(monkeypatch):
    node = TagQueryNode(["t1"], interval="60s", period=1)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/queues/by_tag"
        assert request.url.params.get("match_mode") == "any"
        return httpx.Response(200, json={"queues": ["q1"]})

    transport = httpx.MockTransport(handler)

    class DummyClient:
        def __init__(self, *a, **k):
            self._client = httpx.Client(transport=transport)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            self._client.close()

        async def get(self, url, params=None):
            request = httpx.Request("GET", url, params=params)
            resp = handler(request)
            resp.request = request
            return resp

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)

    manager = TagQueryManager("http://gw")
    manager.register(node)
    await manager.resolve_tags()
    assert node.upstreams == ["q1"]
    assert node.execute

    await manager.handle_message({
        "event": "queue_update",
        "data": {"tags": ["t1"], "interval": 60, "queues": ["q2"], "match_mode": "any"},
    })
    assert node.upstreams == ["q2"]

    await manager.handle_message({
        "event": "queue_update",
        "data": {"tags": ["t1"], "interval": 60, "queues": [], "match_mode": "any"},
    })
    assert node.upstreams == []
    assert not node.execute

    await manager.stop()


@pytest.mark.asyncio
async def test_resolve_handles_empty(monkeypatch):
    node = TagQueryNode(["t1"], interval="60s", period=1)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"queues": []})

    transport = httpx.MockTransport(handler)

    class DummyClient:
        def __init__(self, *a, **k):
            self._client = httpx.Client(transport=transport)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            self._client.close()

        async def get(self, url, params=None):
            request = httpx.Request("GET", url, params=params)
            resp = handler(request)
            resp.request = request
            return resp

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)

    manager = TagQueryManager("http://gw")
    manager.register(node)
    await manager.resolve_tags()
    assert node.upstreams == []
    assert not node.execute


@pytest.mark.asyncio
async def test_match_mode_routes_updates():
    node_any = TagQueryNode(["t1"], interval="60s", period=1, match_mode="any")
    node_all = TagQueryNode(["t1"], interval="60s", period=1, match_mode="all")
    manager = TagQueryManager()
    manager.register(node_any)
    manager.register(node_all)

    await manager.handle_message({
        "event": "queue_update",
        "data": {"tags": ["t1"], "interval": 60, "queues": ["q1"], "match_mode": "all"},
    })
    assert node_all.upstreams == ["q1"]
    assert node_any.upstreams == []

    await manager.handle_message({
        "event": "queue_update",
        "data": {"tags": ["t1"], "interval": 60, "queues": ["q2"]},
    })
    assert node_any.upstreams == ["q2"]

