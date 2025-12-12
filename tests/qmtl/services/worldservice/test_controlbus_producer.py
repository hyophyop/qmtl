import json
import pytest

from qmtl.services.worldservice.controlbus_producer import ControlBusProducer


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
async def test_publish_policy_update_cloud_event():
    dummy = DummyProducer()
    producer = ControlBusProducer(producer=dummy, topic="policy")
    await producer.publish_policy_update(
        "w1",
        policy_version=1,
        checksum="chk",
        status="ACTIVE",
        ts="2024-01-01T00:00:00Z",
    )
    topic, data, key = dummy.sent[0]
    evt = json.loads(data.decode())
    assert evt["type"] == "policy_updated"
    assert evt["data"]["world_id"] == "w1"
    assert evt["data"]["policy_version"] == 1
    assert evt["data"]["checksum"] == "chk"
    assert evt["data"]["status"] == "ACTIVE"
    assert evt["data"]["ts"] == "2024-01-01T00:00:00Z"
    assert topic == "policy"
    assert key == b"w1"


@pytest.mark.asyncio
async def test_publish_activation_update_cloud_event():
    dummy = DummyProducer()
    producer = ControlBusProducer(producer=dummy, topic="activation")
    await producer.publish_activation_update(
        "w1",
        etag="e1",
        run_id="r1",
        ts="2024-01-01T00:00:00Z",
        state_hash="h1",
        payload={"side": "long", "active": True},
    )
    topic, data, key = dummy.sent[0]
    evt = json.loads(data.decode())
    assert evt["type"] == "activation_updated"
    assert evt["data"]["world_id"] == "w1"
    assert evt["data"]["etag"] == "e1"
    assert evt["data"]["run_id"] == "r1"
    assert evt["data"]["state_hash"] == "h1"
    assert evt["data"]["side"] == "long"
    assert evt["data"]["active"] is True
    assert topic == "activation"
    assert key == b"w1"


@pytest.mark.asyncio
async def test_publish_risk_snapshot_updated_preserves_snapshot_version():
    dummy = DummyProducer()
    producer = ControlBusProducer(producer=dummy, topic="risk_snapshot_updated")
    await producer.publish_risk_snapshot_updated(
        "w1",
        {
            "as_of": "2025-01-01T00:00:00Z",
            "version": "snap-v1",
            "weights": {"a": 1.0},
        },
        version=2,
    )
    topic, data, key = dummy.sent[0]
    evt = json.loads(data.decode())
    assert evt["type"] == "risk_snapshot_updated"
    assert evt["data"]["world_id"] == "w1"
    assert evt["data"]["version"] == "snap-v1"
    assert evt["data"]["event_version"] == 2
    assert topic == "risk_snapshot_updated"
    assert key == b"w1"


@pytest.mark.asyncio
async def test_start_warns_when_optional_controlbus_missing(caplog):
    producer = ControlBusProducer(brokers=[], required=False)

    with caplog.at_level("WARNING"):
        await producer.start()

    assert "ControlBus disabled" in caplog.text


@pytest.mark.asyncio
async def test_start_raises_when_controlbus_required_and_missing():
    producer = ControlBusProducer(brokers=[], required=True)

    with pytest.raises(RuntimeError, match="ControlBus unavailable"):
        await producer.start()
