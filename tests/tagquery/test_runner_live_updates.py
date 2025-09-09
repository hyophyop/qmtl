import asyncio
import json
import httpx
import pytest

from qmtl.sdk import Strategy, TagQueryNode, Runner, MatchMode
from qmtl.gateway.api import create_app, Database
from qmtl.gateway.ws import WebSocketHub
from qmtl.common.cloudevents import EVENT_SCHEMA_VERSION


async def wait_for(condition, timeout: float = 1.0) -> None:
    async def _wait() -> None:
        while not condition():
            await asyncio.sleep(0)

    await asyncio.wait_for(_wait(), timeout)


class DummyDag:
    async def get_queues_by_tag(self, tags, interval, match_mode="any", world_id=None):
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
        self.tq = TagQueryNode(["t1"], interval="60s", period=1)
        self.add_nodes([self.tq])


@pytest.mark.asyncio
async def test_live_auto_subscribes(monkeypatch, fake_redis):
    class DummyWS:
        def __init__(self, url, *, token=None, on_message=None):
            self.on_message = on_message
            self.token = token

        async def start(self):
            pass

        async def stop(self):
            pass

        async def _handle(self, data):
            if self.on_message:
                await self.on_message(data)

    class DummyHub(WebSocketHub):
        def __init__(self, client):
            super().__init__()
            self.client = client

        async def send_queue_update(self, tags, interval, queues, match_mode: MatchMode = MatchMode.ANY):  # type: ignore[override]
            await self.client._handle(
                {
                    "type": "queue_update",
                    "data": {
                        "tags": tags,
                        "interval": interval,
                        "queues": queues,
                        "match_mode": match_mode.value,
                        "version": EVENT_SCHEMA_VERSION,
                    },
                }
            )

    client = DummyWS("ws://dummy")

    def ws_factory(url, *, on_message=None, token=None):
        client.on_message = on_message
        client.token = token
        return client
    hub = DummyHub(client)
    redis = fake_redis
    gw_app = create_app(dag_client=DummyDag(), ws_hub=hub, redis_client=redis, database=FakeDB(), enable_background=False)
    transport = httpx.ASGITransport(gw_app)

    real_client = httpx.AsyncClient
    monkeypatch.setattr("qmtl.sdk.tagquery_manager.WebSocketClient", ws_factory)

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

        async def post(self, url, json=None):
            return await self._client.post(url, json=json)

        async def get(self, url, params=None):
            return await self._client.get(url, params=params)

    monkeypatch.setattr("qmtl.sdk.gateway_client.httpx.AsyncClient", DummyClient)
    monkeypatch.setattr("qmtl.sdk.tagquery_manager.httpx.AsyncClient", DummyClient)
    monkeypatch.setattr(Runner, "_kafka_available", True)

    async with Runner.session(
        TQStrategy, world_id="tq_live_updates", gateway_url="http://gw"
    ) as strat:
        await wait_for(lambda: bool(strat.tag_query_manager._nodes))

        await hub.send_queue_update(
            ["t1"],
            60,
            [{"queue": "q1", "global": False}],
            MatchMode.ANY,
        )
        await strat.tag_query_manager.handle_message(
            {
                "type": "queue_update",
                "data": {
                    "tags": ["t1"],
                    "interval": 60,
                    "queues": [{"queue": "q1", "global": False}],
                    "match_mode": "any",
                    "version": EVENT_SCHEMA_VERSION,
                },
            }
        )

        node = strat.tq
        await wait_for(lambda: node.upstreams == ["q1"])
        assert node.execute
        assert hasattr(strat, "tag_query_manager")
    await transport.aclose()
