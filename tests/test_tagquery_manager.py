import asyncio
import httpx
import pytest

from qmtl.sdk import TagQueryNode, MatchMode
from qmtl.sdk.tagquery_manager import TagQueryManager
from qmtl.common.cloudevents import EVENT_SCHEMA_VERSION


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
                "version": EVENT_SCHEMA_VERSION,
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
                "version": EVENT_SCHEMA_VERSION,
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
                "version": EVENT_SCHEMA_VERSION,
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
                "version": EVENT_SCHEMA_VERSION,
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
            await self.on_message(
                {
                    "event": "queue_update",
                    "data": {
                        "tags": ["t1"],
                        "interval": 60,
                        "queues": [{"queue": "q3", "global": False}],
                        "match_mode": "any",
                        "version": EVENT_SCHEMA_VERSION,
                    },
                }
            )

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

