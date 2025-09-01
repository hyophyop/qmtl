import asyncio
import json
import httpx
import pytest

from qmtl.sdk import TagQueryNode, MatchMode
from qmtl.sdk.tagquery_manager import TagQueryManager


@pytest.mark.asyncio
async def test_resolve_and_update(monkeypatch):
    node = TagQueryNode(["t1"], interval="60s", period=1)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/queues/by_tag"
        assert request.url.params.get("match_mode") == "any"
        return httpx.Response(
            200, json={"queues": [{"queue": "q1", "global": False}]}
        )

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

    await manager.handle_message(
        {
            "event": "queue_update",
            "data": {
                "tags": ["t1"],
                "interval": 60,
                "queues": [{"queue": "q2", "global": False}],
                "match_mode": "any",
            },
        }
    )
    assert node.upstreams == ["q2"]

    await manager.handle_message(
        {
            "event": "queue_update",
            "data": {
                "tags": ["t1"],
                "interval": 60,
                "queues": [],
                "match_mode": "any",
            },
        }
    )
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
    node_any = TagQueryNode(["t1"], interval="60s", period=1, match_mode=MatchMode.ANY)
    node_all = TagQueryNode(["t1"], interval="60s", period=1, match_mode=MatchMode.ALL)
    manager = TagQueryManager()
    manager.register(node_any)
    manager.register(node_all)

    await manager.handle_message(
        {
            "event": "queue_update",
            "data": {
                "tags": ["t1"],
                "interval": 60,
                "queues": [{"queue": "q1", "global": False}],
                "match_mode": "all",
            },
        }
    )
    assert node_all.upstreams == ["q1"]
    assert node_any.upstreams == []

    await manager.handle_message(
        {
            "event": "queue_update",
            "data": {
                "tags": ["t1"],
                "interval": 60,
                "queues": [{"queue": "q2", "global": False}],
            },
        }
    )
    assert node_any.upstreams == ["q2"]


@pytest.mark.asyncio
async def test_resolve_filters_global(monkeypatch):
    node = TagQueryNode(["t1"], interval="60s", period=1)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "queues": [
                    {"queue": "q1", "global": True},
                    {"queue": "q2", "global": False},
                ]
            },
        )

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
    assert node.upstreams == ["q2"]


@pytest.mark.asyncio
async def test_start_uses_event_descriptor(monkeypatch):
    node = TagQueryNode(["t1"], interval="60s", period=1)
    manager = TagQueryManager("http://gw", world_id="w1", strategy_id="s1")
    manager.register(node)

    class DummyWS:
        def __init__(self, url: str, *, token: str | None = None, on_message=None, **_):
            self.url = url
            self.token = token
            self.on_message = on_message
            self.started = False

        async def start(self):
            self.started = True
            await self.on_message({
                "event": "queue_update",
            "data": {
                "tags": ["t1"],
                "interval": 60,
                "queues": [{"queue": "q3", "global": False}],
                "match_mode": "any",
            },
            })

        async def stop(self):
            self.started = False

    posted = {"body": None}

    async def fake_post(self, url, json=None):
        posted["body"] = json
        return httpx.Response(200, json={"stream_url": "wss://evt", "token": "tok"})

    async def aenter(self):
        return self

    async def aexit(self, exc_type, exc, tb):
        pass

    FakeClient = type("FakeClient", (), {"__aenter__": aenter, "__aexit__": aexit, "post": fake_post})
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: FakeClient())
    monkeypatch.setattr("qmtl.sdk.tagquery_manager.WebSocketClient", DummyWS)

    await manager.start()
    assert isinstance(manager.client, DummyWS)
    assert manager.client.url == "wss://evt"
    assert manager.client.token == "tok"
    assert posted["body"]["world_id"] == "w1"
    assert posted["body"]["strategy_id"] == "s1"
    assert node.upstreams == ["q3"]
    await manager.stop()


@pytest.mark.asyncio
async def test_start_falls_back_to_watch(monkeypatch):
    node = TagQueryNode(["t1"], interval="60s", period=1)
    manager = TagQueryManager("http://gw")
    manager.register(node)

    class Stream:
        def __init__(self, lines):
            self._lines = lines

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def aiter_lines(self):
            for line in self._lines:
                yield line

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def post(self, url, json=None):
            return httpx.Response(404)

        async def get(self, url, params=None):
            resp = httpx.Response(200, json={"queues": []})
            resp.request = httpx.Request("GET", url, params=params)
            return resp

        def stream(self, method, url, params=None):
            data = json.dumps({"queues": [{"queue": "q4", "global": False}]})
            return Stream([data])

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: DummyClient())

    await manager.start()
    await asyncio.sleep(0.05)
    assert manager.client is None
    assert node.upstreams == ["q4"]
    await manager.stop()


@pytest.mark.asyncio
async def test_watch_reconnects(monkeypatch):
    node = TagQueryNode(["t1"], interval="60s", period=1)
    manager = TagQueryManager("http://gw")
    manager.register(node)

    calls = {"count": 0}

    class Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def aiter_lines(self):
            calls["count"] += 1
            if calls["count"] == 1:
                yield json.dumps({"queues": [{"queue": "q1", "global": False}]})
            else:
                yield json.dumps({"queues": [{"queue": "q2", "global": False}]})

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def post(self, url, json=None):
            return httpx.Response(404)

        async def get(self, url, params=None):
            resp = httpx.Response(200, json={"queues": []})
            resp.request = httpx.Request("GET", url, params=params)
            return resp

        def stream(self, method, url, params=None):
            return Stream()

    orig_sleep = asyncio.sleep

    async def fast_sleep(_):
        await orig_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: DummyClient())

    await manager.start()
    await orig_sleep(0.1)
    assert node.upstreams == ["q2"]
    await manager.stop()
