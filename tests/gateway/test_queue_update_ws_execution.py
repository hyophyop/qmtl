import asyncio
import httpx
import pytest

from qmtl.gateway.api import create_app
from qmtl.gateway.ws import WebSocketHub
from qmtl.sdk import TagQueryNode, Runner
from qmtl.sdk.ws_client import WebSocketClient
from qmtl.common.cloudevents import format_event


class DummyDag:
    async def get_queues_by_tag(self, tags, interval):
        return []


class DummyHub(WebSocketHub):
    def __init__(self, client: WebSocketClient) -> None:
        super().__init__()
        self.client = client

    async def send_queue_update(self, tags, interval, queues):  # type: ignore[override]
        await self.client._handle({
            "type": "queue_update",
            "data": {"tags": tags, "interval": interval, "queues": queues},
        })


@pytest.mark.asyncio
async def test_node_unpauses_on_queue_update():
    client = WebSocketClient("ws://dummy")
    ws_hub = DummyHub(client)
    gw_app = create_app(dag_client=DummyDag(), ws_hub=ws_hub)
    transport = httpx.ASGITransport(gw_app)
    calls = []
    node = TagQueryNode(["t1"], interval=60, period=1, compute_fn=lambda v: calls.append(v))
    client.register_tag_query_node(node)

    assert not node.execute

    event = format_event(
        "qmtl.dagmanager",
        "queue_update",
        {"tags": ["t1"], "interval": 60, "queues": ["q1"]},
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/callbacks/dag-event", json=event)
        assert resp.status_code == 202

    await asyncio.sleep(0.2)

    assert node.execute
    assert node.upstreams == ["q1"]

    Runner.feed_queue_data(node, "q1", 60, 60, {"v": 1})
    assert calls

    await client.stop()
