import json

import pytest

from qmtl.services.gateway.controlbus_ack import ActivationAckProducer


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
async def test_activation_ack_publisher_emits_cloudevent_with_idempotency_key():
    ack = ActivationAckProducer(brokers=["kafka:9092"], topic="control.activation.ack")
    dummy = DummyProducer()
    ack._producer = dummy  # test seam

    await ack.publish_ack(
        world_id="w1",
        run_id="r1",
        sequence=3,
        phase="apply",
        etag="e1",
    )

    topic, data, key = dummy.sent[0]
    evt = json.loads(data.decode())
    assert evt["type"] == "activation_ack"
    assert evt["correlation_id"] == "activation:w1:r1"
    assert evt["data"]["world_id"] == "w1"
    assert evt["data"]["run_id"] == "r1"
    assert evt["data"]["sequence"] == 3
    assert evt["data"]["phase"] == "apply"
    assert evt["data"]["etag"] == "e1"
    assert "idempotency_key" in evt["data"]
    assert topic == "control.activation.ack"
    assert key == b"w1"

