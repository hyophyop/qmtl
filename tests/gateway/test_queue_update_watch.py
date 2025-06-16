import asyncio
import httpx
import pytest
import json

from qmtl.gateway.api import create_app
from qmtl.gateway.watch import QueueWatchHub
from qmtl.sdk import TagQueryNode
from qmtl.common.cloudevents import format_event

class DummyDag:
    async def get_queues_by_tag(self, tags, interval):
        return []

@pytest.mark.asyncio
async def test_queue_update_reaches_subscriber(monkeypatch):
    watch = QueueWatchHub()
    gw_app = create_app(dag_client=DummyDag(), watch_hub=watch)
    transport = httpx.ASGITransport(gw_app)

    real_client = httpx.AsyncClient

    class DummyStream:
        def __init__(self, gen):
            self._gen = gen

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            await self._gen.aclose()

        async def aiter_lines(self):
            async for queues in self._gen:
                yield json.dumps({"queues": queues})

    class DummyClient:
        def __init__(self, *a, **k):
            self._client = real_client(*a, **k)

        async def __aenter__(self):
            await self._client.__aenter__()
            return self

        async def __aexit__(self, exc_type, exc, tb):
            await self._client.__aexit__(exc_type, exc, tb)

        def stream(self, method, url, params=None):
            if url.endswith("/queues/watch"):
                gen = watch.subscribe(["t1"], 60)
                return DummyStream(gen)
            return self._client.stream(method, url, params=params)

        async def post(self, url, json=None):
            return await self._client.post(url, json=json)

    monkeypatch.setattr("qmtl.sdk.node.httpx.AsyncClient", DummyClient)

    node = TagQueryNode(["t1"], interval=60, period=1)
    task = asyncio.create_task(node.subscribe_updates("http://gw"))
    await asyncio.sleep(0.2)

    event = format_event(
        "qmtl.dagmanager",
        "queue_update",
        {"tags": ["t1"], "interval": 60, "queues": ["q1"]},
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://gw") as c:
        resp = await c.post("/callbacks/dag-event", json=event)
        assert resp.status_code == 202

    await asyncio.sleep(0.1)
    assert node.upstreams == ["q1"]

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_node_completed_reaches_subscriber(monkeypatch):
    watch = QueueWatchHub()
    gw_app = create_app(dag_client=DummyDag(), watch_hub=watch)
    transport = httpx.ASGITransport(gw_app)

    real_client = httpx.AsyncClient

    class DummyStream:
        def __init__(self, gen):
            self._gen = gen

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            await self._gen.aclose()

        async def aiter_lines(self):
            async for queues in self._gen:
                yield json.dumps({"queues": queues})

    class DummyClient:
        def __init__(self, *a, **k):
            self._client = real_client(*a, **k)

        async def __aenter__(self):
            await self._client.__aenter__()
            return self

        async def __aexit__(self, exc_type, exc, tb):
            await self._client.__aexit__(exc_type, exc, tb)

        def stream(self, method, url, params=None):
            if url.endswith("/queues/watch"):
                gen = watch.subscribe(["t1"], 60)
                return DummyStream(gen)
            return self._client.stream(method, url, params=params)

        async def post(self, url, json=None):
            return await self._client.post(url, json=json)

    monkeypatch.setattr("qmtl.sdk.node.httpx.AsyncClient", DummyClient)

    node = TagQueryNode(["t1"], interval=60, period=1)
    task = asyncio.create_task(node.subscribe_updates("http://gw"))
    await asyncio.sleep(0.2)

    event = format_event(
        "qmtl.dagmanager",
        "queue_update",
        {"tags": ["t1"], "interval": 60, "queues": []},
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://gw") as c:
        resp = await c.post("/callbacks/dag-event", json=event)
        assert resp.status_code == 202

    await asyncio.sleep(0.1)
    assert node.upstreams == []

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
