import asyncio
import pytest

from qmtl.gateway.ws import WebSocketHub
from qmtl.sdk import TagQueryNode, Runner, MatchMode
from qmtl.sdk.ws_client import WebSocketClient
from qmtl.sdk.tagquery_manager import TagQueryManager


class DummyDag:
    async def get_queues_by_tag(self, tags, interval, match_mode="any", world_id=None):
        return []


class DummyHub(WebSocketHub):
    def __init__(self, client: WebSocketClient) -> None:
        super().__init__()
        self.client = client

    async def send_queue_update(self, tags, interval, queues, match_mode: MatchMode = MatchMode.ANY):  # type: ignore[override]
        await self.client._handle({
            "type": "queue_update",
            "data": {
                "tags": tags,
                "interval": interval,
                "queues": queues,
                "match_mode": match_mode.value,
            },
        })


@pytest.mark.asyncio
async def test_node_unpauses_on_queue_update():
    client = WebSocketClient("ws://dummy")
    manager = TagQueryManager(ws_client=client)
    ws_hub = DummyHub(client)
    calls = []
    node = TagQueryNode(["t1"], interval="60s", period=1, compute_fn=lambda v: calls.append(v))
    manager.register(node)

    assert not node.execute

    await ws_hub.send_queue_update(
        ["t1"],
        60,
        [{"queue": "q1", "global": False}],
        MatchMode.ANY,
    )

    assert node.execute
    assert node.upstreams == ["q1"]

    Runner.feed_queue_data(node, "q1", 60, 60, {"v": 1})
    assert calls

    await manager.stop()
    await client.stop()
