import asyncio
import json
import httpx
import pytest

from qmtl.sdk import Strategy, TagQueryNode, Runner
from qmtl.gateway.api import create_app, Database
from qmtl.gateway.watch import QueueWatchHub
from qmtl.common.cloudevents import format_event
from fakeredis.aioredis import FakeRedis


class DummyDag:
    async def get_queues_by_tag(self, tags, interval):
        return []


class FakeDB(Database):
    async def insert_strategy(self, strategy_id: str, meta=None):
        pass

    async def set_status(self, strategy_id: str, status: str) -> None:
        pass

    async def get_status(self, strategy_id: str):
        return None

    async def append_event(self, strategy_id: str, event: str) -> None:  # pragma: no cover - not used
        pass


class TQStrategy(Strategy):
    def setup(self):
        self.tq = TagQueryNode(["t1"], interval=60, period=1)
        self.add_nodes([self.tq])


@pytest.mark.asyncio
async def test_live_auto_subscribes(monkeypatch):
    watch = QueueWatchHub()
    redis = FakeRedis(decode_responses=True)
    gw_app = create_app(dag_client=DummyDag(), watch_hub=watch, redis_client=redis, database=FakeDB())
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
            k.setdefault("transport", transport)
            k.setdefault("base_url", "http://gw")
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

        async def get(self, url, params=None):
            return await self._client.get(url, params=params)

    monkeypatch.setattr("qmtl.sdk.runner.httpx.AsyncClient", DummyClient)
    monkeypatch.setattr("qmtl.sdk.node.httpx.AsyncClient", DummyClient)

    strat = await Runner.live_async(TQStrategy, gateway_url="http://gw")

    await asyncio.sleep(0.1)

    event = format_event(
        "qmtl.dagmanager",
        "queue_update",
        {"tags": ["t1"], "interval": 60, "queues": ["q1"]},
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://gw") as c:
        resp = await c.post("/callbacks/dag-event", json=event)
        assert resp.status_code == 202

    await asyncio.sleep(0.1)
    node = strat.tq
    assert node.upstreams == ["q1"]
    assert node.execute
    assert hasattr(strat, "update_tasks") and strat.update_tasks

    for t in strat.update_tasks:
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t
