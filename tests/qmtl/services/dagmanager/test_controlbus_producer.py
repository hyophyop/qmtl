import json

import pytest

from qmtl.services.dagmanager.controlbus_producer import ControlBusProducer


class DummyProducer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes, bytes | None]] = []

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def send_and_wait(self, topic: str, data: bytes, key: bytes | None = None) -> None:
        self.sent.append((topic, data, key))


@pytest.mark.asyncio
async def test_controlbus_producer_emits_queue_update_as_cloudevent():
    dummy = DummyProducer()
    producer = ControlBusProducer(producer=dummy, topic="queue", sentinel_topic="sentinel_weight")

    await producer.publish_queue_update(
        tags=["a", "b"],
        interval=60,
        queues=[{"queue": "q1", "global": True}],
        match_mode="any",
        version=1,
    )

    topic, data, key = dummy.sent[0]
    evt = json.loads(data.decode())
    assert evt["type"] == "queue_updated"
    assert evt["correlation_id"].startswith("queue:")
    assert evt["data"]["etag"].startswith("q:")
    assert "idempotency_key" in evt["data"]
    assert topic == "queue"
    assert key == b"a,b"


@pytest.mark.asyncio
async def test_controlbus_producer_emits_sentinel_weight_as_cloudevent():
    dummy = DummyProducer()
    producer = ControlBusProducer(producer=dummy, topic="queue", sentinel_topic="sentinel_weight")

    await producer.publish_sentinel_weight(
        sentinel_id="s1",
        weight=0.25,
        world_id="w1",
        version=1,
    )

    topic, data, key = dummy.sent[0]
    evt = json.loads(data.decode())
    assert evt["type"] == "sentinel_weight_updated"
    assert evt["data"]["sentinel_id"] == "s1"
    assert evt["data"]["weight"] == 0.25
    assert "idempotency_key" in evt["data"]
    assert topic == "sentinel_weight"
    assert key == b"s1"

