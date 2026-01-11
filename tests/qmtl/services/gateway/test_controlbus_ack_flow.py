import asyncio
import json
import time

import pytest

from qmtl.services.gateway.controlbus_ack import ActivationAckProducer
from qmtl.services.gateway.controlbus_consumer import ControlBusConsumer
from qmtl.services.worldservice.controlbus_producer import ControlBusProducer


class DummyProducer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes, bytes | None]] = []
        self.sent_event = asyncio.Event()

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def send_and_wait(self, topic: str, data: bytes, key: bytes | None = None) -> None:
        self.sent.append((topic, data, key))
        self.sent_event.set()


class FakeKafkaMessage:
    def __init__(self, *, topic: str, value: bytes, key: bytes | None, headers=None, timestamp: float | None = None) -> None:
        self.topic = topic
        self.value = value
        self.key = key
        self.headers = headers or []
        self.timestamp = timestamp


@pytest.mark.asyncio
async def test_activation_update_requires_ack_emits_gateway_ack():
    bus_dummy = DummyProducer()
    ws_bus = ControlBusProducer(producer=bus_dummy, topic="activation")

    await ws_bus.publish_activation_update(
        "w1",
        etag="e1",
        run_id="r1",
        ts="2024-01-01T00:00:00Z",
        state_hash="h1",
        payload={"phase": "apply", "strategy_id": "s1", "side": "long"},
        requires_ack=True,
        sequence=7,
    )

    topic, data, key = bus_dummy.sent[0]

    ack_dummy = DummyProducer()
    ack_producer = ActivationAckProducer(brokers=["kafka:9092"], topic="control.activation.ack")
    ack_producer._producer = ack_dummy

    consumer = ControlBusConsumer(
        brokers=[],
        topics=["activation"],
        group="gateway",
        ack_producer=ack_producer,
    )

    await consumer.start()
    cb_msg = consumer._parse_kafka_message(
        FakeKafkaMessage(topic=topic, value=data, key=key, timestamp=time.time() * 1000)
    )

    assert cb_msg.data.get("requires_ack") is True
    assert cb_msg.data.get("sequence") == 7

    await consumer.publish(cb_msg)
    await consumer._queue.join()
    await asyncio.wait_for(ack_dummy.sent_event.wait(), timeout=1)
    await consumer.stop()

    ack_topic, ack_data, ack_key = ack_dummy.sent[0]
    ack_evt = json.loads(ack_data.decode())

    assert ack_topic == "control.activation.ack"
    assert ack_key == b"w1"
    assert ack_evt["type"] == "activation_ack"
    assert ack_evt["correlation_id"] == "activation:w1:r1"
    assert ack_evt["data"]["world_id"] == "w1"
    assert ack_evt["data"]["run_id"] == "r1"
    assert ack_evt["data"]["sequence"] == 7
    assert ack_evt["data"]["phase"] == "apply"
    assert ack_evt["data"]["etag"] == "e1"
    assert "idempotency_key" in ack_evt["data"]
