import asyncio

import httpx
from qmtl.runtime.sdk import MatchMode, Strategy, TagQueryNode
from qmtl.runtime.sdk.tag_manager_service import TagManagerService


async def wait_for(condition, timeout: float = 1.0) -> None:
    async def _wait() -> None:
        while not condition():
            await asyncio.sleep(0)

    await asyncio.wait_for(_wait(), timeout)


class TQStrategy(Strategy):
    def setup(self):
        self.tq = TagQueryNode(["t1"], interval="60s", period=1)
        self.add_nodes([self.tq])


def test_live_auto_subscribes(monkeypatch):
    async def run_case():
        class DummyWS:
            def __init__(self, url, *, token=None, on_message=None):
                self.url = url
                self.on_message = on_message
                self.token = token

            async def start(self):
                pass

            async def stop(self):
                pass

            async def _handle(self, data):
                if self.on_message:
                    await self.on_message(data)

        client = DummyWS("ws://dummy")

        def ws_factory(url, *, on_message=None, token=None):
            client.on_message = on_message
            client.token = token
            return client

        monkeypatch.setattr("qmtl.runtime.sdk.tagquery_manager.WebSocketClient", ws_factory)

        class DummyClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def post(self, url, json=None):
                if url.endswith("/strategies"):
                    return httpx.Response(200, json={"strategy_id": "s-live", "queue_map": {}})
                if url.endswith("/events/subscribe"):
                    return httpx.Response(
                        200,
                        json={
                            "stream_url": "ws://dummy",
                            "token": "tok-live",
                            "topics": ["w/tq_live_updates/queues"],
                        },
                    )
                raise AssertionError(f"unexpected POST {url}")

            async def get(self, url, params=None):
                if url.endswith("/queues/by_tag"):
                    return httpx.Response(200, json={"queues": []})
                raise AssertionError(f"unexpected GET {url}")

        monkeypatch.setattr("qmtl.runtime.sdk.tagquery_manager.httpx.AsyncClient", DummyClient)
        strat = TQStrategy()
        strat.setup()
        manager = TagManagerService("http://gw").init(
            strat,
            world_id="tq_live_updates",
            strategy_id="s-live",
        )
        try:
            await manager.start()
            await wait_for(lambda: bool(manager._nodes))

            await client._handle(
                {
                    "type": "queue_update",
                    "data": {
                        "tags": ["t1"],
                        "interval": 60,
                        "queues": [{"queue": "q1", "global": False}],
                        "match_mode": MatchMode.ANY.value,
                        "etag": "q:t1:60:1",
                        "ts": "2020-01-01T00:00:00Z",
                        "version": 1,
                        },
                    }
                )
            await manager.handle_message(
                {
                    "type": "queue_update",
                    "data": {
                        "tags": ["t1"],
                        "interval": 60,
                        "queues": [{"queue": "q1", "global": False}],
                        "match_mode": "any",
                        "etag": "q:t1:60:1",
                        "ts": "2020-01-01T00:00:00Z",
                        "version": 1,
                    },
                }
            )

            node = strat.tq
            await wait_for(lambda: node.upstreams == ["q1"])
            assert node.execute
            assert hasattr(strat, "tag_query_manager")
            assert strat.tag_query_manager is manager
        finally:
            await manager.stop()

    asyncio.run(run_case())
