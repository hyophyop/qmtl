import asyncio
import json
import time
from typing import Any

import pytest

from qmtl.services.gateway.controlbus_ack import ActivationAckProducer
from qmtl.services.gateway.controlbus_consumer import (
    ControlBusConsumer,
    ControlBusMessage,
)
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


class DelayedDummyProducer(DummyProducer):
    def __init__(self, delays_by_sequence: dict[int, float] | None = None) -> None:
        super().__init__()
        self._delays_by_sequence = delays_by_sequence or {}

    async def send_and_wait(self, topic: str, data: bytes, key: bytes | None = None) -> None:
        sequence = int(json.loads(data.decode())["data"]["sequence"])
        await asyncio.sleep(self._delays_by_sequence.get(sequence, 0.0))
        await super().send_and_wait(topic, data, key=key)


class FakeKafkaMessage:
    def __init__(self, *, topic: str, value: bytes, key: bytes | None, headers=None, timestamp: float | None = None) -> None:
        self.topic = topic
        self.value = value
        self.key = key
        self.headers = headers or []
        self.timestamp = timestamp


class FakeHub:
    def __init__(self) -> None:
        self.activations: list[dict[str, Any]] = []

    async def send_activation_updated(self, data: dict[str, Any]) -> None:
        self.activations.append(data)


def _activation_message(*, world_id: str, run_id: str, sequence: int) -> ControlBusMessage:
    return ControlBusMessage(
        topic="activation",
        key=world_id,
        etag=f"etag-{run_id}-{sequence}",
        run_id=run_id,
        data={
            "version": 1,
            "world_id": world_id,
            "run_id": run_id,
            "requires_ack": True,
            "sequence": sequence,
            "phase": "apply",
            "etag": f"etag-{run_id}-{sequence}",
            "ts": "2024-01-01T00:00:00Z",
            "strategy_id": "s1",
        },
        timestamp_ms=time.time() * 1000,
    )


def _ack_sequences(sent: list[tuple[str, bytes, bytes | None]]) -> list[int]:
    return [int(json.loads(data.decode())["data"]["sequence"]) for _, data, _ in sent]


def _ack_run_ids(sent: list[tuple[str, bytes, bytes | None]]) -> list[str]:
    return [str(json.loads(data.decode())["data"]["run_id"]) for _, data, _ in sent]


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

    assert (cb_msg.data.get("requires_ack"), cb_msg.data.get("sequence")) == (True, 7)

    await consumer.publish(cb_msg)
    await consumer._queue.join()
    await asyncio.wait_for(ack_dummy.sent_event.wait(), timeout=1)
    await consumer.stop()

    ack_topic, ack_data, ack_key = ack_dummy.sent[0]
    ack_evt = json.loads(ack_data.decode())
    ack_payload = dict(ack_evt["data"])
    idempotency_key = ack_payload.pop("idempotency_key", None)

    assert (
        ack_topic,
        ack_key,
        ack_evt["type"],
        ack_evt["correlation_id"],
    ) == (
        "control.activation.ack",
        b"w1",
        "activation_ack",
        "activation:w1:r1",
    )
    assert {k: ack_payload[k] for k in ("world_id", "run_id", "sequence", "phase", "etag")} == {
        "world_id": "w1",
        "run_id": "r1",
        "sequence": 7,
        "phase": "apply",
        "etag": "e1",
    }
    assert idempotency_key


@pytest.mark.asyncio
async def test_activation_sequence_out_of_order_buffer_and_gap_fill_release() -> None:
    hub = FakeHub()
    ack_dummy = DelayedDummyProducer(delays_by_sequence={11: 0.03, 12: 0.0})
    ack_producer = ActivationAckProducer(
        brokers=["kafka:9092"],
        topic="control.activation.ack",
    )
    ack_producer._producer = ack_dummy

    consumer = ControlBusConsumer(
        brokers=[],
        topics=["activation"],
        group="gateway",
        ws_hub=hub,
        ack_producer=ack_producer,
    )
    await consumer.start()

    await consumer.publish(_activation_message(world_id="w1", run_id="r1", sequence=10))
    await consumer._queue.join()
    assert [evt["sequence"] for evt in hub.activations] == [10]
    assert _ack_sequences(ack_dummy.sent) == [10]

    await consumer.publish(_activation_message(world_id="w1", run_id="r1", sequence=12))
    await consumer._queue.join()
    assert [evt["sequence"] for evt in hub.activations] == [10]
    assert _ack_sequences(ack_dummy.sent) == [10]

    await consumer.publish(_activation_message(world_id="w1", run_id="r1", sequence=11))
    await consumer._queue.join()
    await consumer.stop()

    assert [evt["sequence"] for evt in hub.activations] == [10, 11, 12]
    assert _ack_sequences(ack_dummy.sent) == [10, 11, 12]


@pytest.mark.asyncio
async def test_activation_sequence_ignores_stale_lower_sequence() -> None:
    hub = FakeHub()
    ack_dummy = DummyProducer()
    ack_producer = ActivationAckProducer(
        brokers=["kafka:9092"],
        topic="control.activation.ack",
    )
    ack_producer._producer = ack_dummy

    consumer = ControlBusConsumer(
        brokers=[],
        topics=["activation"],
        group="gateway",
        ws_hub=hub,
        ack_producer=ack_producer,
    )
    await consumer.start()

    await consumer.publish(_activation_message(world_id="w2", run_id="r-stale", sequence=5))
    await consumer.publish(_activation_message(world_id="w2", run_id="r-stale", sequence=4))
    await consumer._queue.join()
    await consumer.stop()

    assert [evt["sequence"] for evt in hub.activations] == [5]
    assert _ack_sequences(ack_dummy.sent) == [5]


@pytest.mark.asyncio
async def test_activation_sequence_resets_for_new_run_id() -> None:
    hub = FakeHub()
    ack_dummy = DummyProducer()
    ack_producer = ActivationAckProducer(
        brokers=["kafka:9092"],
        topic="control.activation.ack",
    )
    ack_producer._producer = ack_dummy

    consumer = ControlBusConsumer(
        brokers=[],
        topics=["activation"],
        group="gateway",
        ws_hub=hub,
        ack_producer=ack_producer,
    )
    await consumer.start()

    await consumer.publish(_activation_message(world_id="w3", run_id="r-old", sequence=8))
    await consumer.publish(_activation_message(world_id="w3", run_id="r-old", sequence=9))
    await consumer.publish(_activation_message(world_id="w3", run_id="r-new", sequence=1))
    await consumer._queue.join()
    await consumer.stop()

    assert [(evt["run_id"], evt["sequence"]) for evt in hub.activations] == [
        ("r-old", 8),
        ("r-old", 9),
        ("r-new", 1),
    ]
    assert list(zip(_ack_run_ids(ack_dummy.sent), _ack_sequences(ack_dummy.sent))) == [
        ("r-old", 8),
        ("r-old", 9),
        ("r-new", 1),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("drop_sequence", "sequence_value"),
    [
        (True, None),
        (False, "not-an-int"),
    ],
)
async def test_activation_requires_ack_with_missing_or_invalid_sequence_drops_without_ws_or_ack(
    drop_sequence: bool,
    sequence_value: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    hub = FakeHub()
    ack_dummy = DummyProducer()
    ack_producer = ActivationAckProducer(
        brokers=["kafka:9092"],
        topic="control.activation.ack",
    )
    ack_producer._producer = ack_dummy

    consumer = ControlBusConsumer(
        brokers=[],
        topics=["activation"],
        group="gateway",
        ws_hub=hub,
        ack_producer=ack_producer,
    )
    await consumer.start()

    msg = _activation_message(world_id="w4", run_id="r-invalid", sequence=1)
    if drop_sequence:
        msg.data.pop("sequence", None)
    else:
        msg.data["sequence"] = sequence_value

    with caplog.at_level("WARNING"):
        await consumer.publish(msg)
        await consumer._queue.join()
        await asyncio.sleep(0)
    await consumer.stop()

    assert hub.activations == []
    assert ack_dummy.sent == []
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(ack_dummy.sent_event.wait(), timeout=0.05)
    assert any(
        "dropping activation message with requires_ack=true due to missing or invalid sequence"
        in record.message
        for record in caplog.records
    )
