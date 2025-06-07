import json
import pytest
import httpx

from qmtl.sdk import TagQueryNode


def test_resolve(monkeypatch):
    node = TagQueryNode(["t1"], interval=60, period=2)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/queues/by_tag"
        assert request.url.params["tags"] == "t1"
        assert request.url.params["interval"] == "60"
        return httpx.Response(200, json={"queues": ["q1", "q2"]})

    transport = httpx.MockTransport(handler)

    def mock_get(url, params=None):
        with httpx.Client(transport=transport) as client:
            return client.get(url, params=params)

    monkeypatch.setattr(httpx, "get", mock_get)

    node.resolve("http://gw")
    assert node.upstreams == ["q1", "q2"]


@pytest.mark.asyncio
async def test_subscribe_updates(monkeypatch):
    node = TagQueryNode(["t1"], interval=60, period=2)

    class DummyStream:
        def __init__(self, lines):
            self._lines = lines
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            pass
        async def aiter_lines(self):
            for l in self._lines:
                yield json.dumps(l)

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            pass
        def stream(self, method, url, params=None):
            assert method == "GET"
            assert url.endswith("/queues/watch")
            assert params["tags"] == "t1"
            assert params["interval"] == 60
            return DummyStream([{"queues": ["q3"]}, {"queues": ["q4"]}])

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)

    await node.subscribe_updates("http://gw")
    assert node.upstreams == ["q4"]
