import json
import logging
import time

import pytest

from tests.helpers.metrics import mapping_store
from qmtl.services.gateway import metrics
from qmtl.services.gateway.ws import WebSocketHub
from qmtl.services.dagmanager.kafka_admin import compute_key, partition_key


class DummyWS:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.client = ("test", 0)

    async def send_text(self, msg: str) -> None:
        self.messages.append(msg)

    async def accept(self) -> None:
        pass


@pytest.mark.asyncio
async def test_hub_broadcasts_progress_and_queue_map():
    hub = WebSocketHub()
    await hub.start()
    ws = DummyWS()
    await hub.connect(ws)
    await hub.send_progress("s1", "queued")
    await hub.send_queue_map(
        "s1",
        {
            partition_key(
                "n1",
                None,
                None,
                compute_key=compute_key("n1"),
            ): "t1"
        },
    )
    await hub.drain()
    await hub.stop()
    assert len(ws.messages) == 2
    types = {json.loads(m)["type"] for m in ws.messages}
    assert "progress" in types
    assert "queue_map" in types


@pytest.mark.asyncio
async def test_hub_line_rate_500_msgs_per_sec():
    hub = WebSocketHub()
    await hub.start()
    ws = DummyWS()
    await hub.connect(ws)
    total = 1000
    start = time.perf_counter()
    for i in range(total):
        await hub.send_progress("s", str(i))
    await hub.drain()
    duration = time.perf_counter() - start
    await hub.stop()
    assert len(ws.messages) == total
    assert len(ws.messages) / duration >= 500


@pytest.mark.asyncio
async def test_hub_logs_send_errors(caplog):
    hub = WebSocketHub()
    await hub.start()

    class BadWS:
        client = ("dummy", 1234)

        async def send_text(self, msg: str) -> None:  # pragma: no cover - exercised in test
            raise RuntimeError("boom")

        async def accept(self) -> None:
            pass

    await hub.connect(BadWS())

    with caplog.at_level(logging.WARNING):
        await hub.send_progress("s1", "queued")
        await hub.drain()
    await hub.stop()
    assert any(
        "Failed to send message to client" in record.message for record in caplog.records
    )


@pytest.mark.asyncio
async def test_hub_sends_sentinel_weight():
    hub = WebSocketHub()
    await hub.start()
    ws = DummyWS()
    await hub.connect(ws)
    await hub.send_sentinel_weight("s1", 0.5)
    await hub.drain()
    await hub.stop()
    msg = json.loads(ws.messages[0])
    assert msg["type"] == "sentinel_weight"
    assert msg["data"] == {"sentinel_id": "s1", "weight": 0.5, "version": 1}


@pytest.mark.asyncio
async def test_hub_sends_activation_and_policy():
    hub = WebSocketHub()
    await hub.start()
    ws = DummyWS()
    await hub.connect(ws)
    await hub.send_activation_updated({"strategy_id": "s1"})
    await hub.send_policy_updated({"strategy_id": "s1", "limit": 1})
    await hub.drain()
    await hub.stop()
    types = {json.loads(m)["type"] for m in ws.messages}
    assert "activation_updated" in types
    assert "policy_updated" in types


@pytest.mark.asyncio
async def test_ws_metrics_fanout_and_drops():
    metrics.reset_metrics()
    hub = WebSocketHub()
    await hub.start()
    ws1 = DummyWS()
    ws2 = DummyWS()
    await hub.connect(ws1, {"t"})
    await hub.connect(ws2, {"t"})
    await hub.broadcast({"msg": 1}, topic="t")
    await hub.drain()
    assert metrics.event_fanout_total.labels(topic="t")._value.get() == 2
    subs_store = mapping_store(metrics.ws_subscribers)
    assert subs_store["t"] == 2

    class BadWS:
        client = ("bad", 0)

        async def send_text(self, msg: str) -> None:
            raise RuntimeError("boom")

        async def accept(self) -> None:
            pass

    bad = BadWS()
    await hub.connect(bad, {"t"})
    await hub.broadcast({"msg": 2}, topic="t")
    await hub.drain()
    assert metrics.ws_dropped_subscribers_total._value.get() == 1
    assert subs_store["t"] == 2

    await hub.disconnect(ws1)
    assert metrics.ws_dropped_subscribers_total._value.get() == 2
    assert subs_store["t"] == 1
    await hub.stop()


@pytest.mark.asyncio
async def test_hub_topic_routing_filters_by_subscription():
    hub = WebSocketHub()
    await hub.start()
    ws_activation = DummyWS()
    ws_policy = DummyWS()
    ws_all = DummyWS()
    await hub.connect(ws_activation, {"activation"})
    await hub.connect(ws_policy, {"policy"})
    await hub.connect(ws_all)
    await hub.send_activation_updated({"strategy_id": "s1"})
    await hub.send_policy_updated({"strategy_id": "s1"})
    await hub.drain()
    await hub.stop()
    act_types = {json.loads(m)["type"] for m in ws_activation.messages}
    pol_types = {json.loads(m)["type"] for m in ws_policy.messages}
    all_types = {json.loads(m)["type"] for m in ws_all.messages}
    assert act_types == {"activation_updated"}
    assert pol_types == {"policy_updated"}
    assert "activation_updated" in all_types and "policy_updated" in all_types
