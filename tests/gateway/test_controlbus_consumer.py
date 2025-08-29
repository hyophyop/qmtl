import asyncio
import time
import pytest

from qmtl.gateway.controlbus_consumer import ControlBusConsumer, ControlBusMessage
from qmtl.gateway.api import create_app, Database
from qmtl.gateway import metrics


class FakeHub:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    async def send_activation_updated(self, data: dict) -> None:
        self.events.append(("activation_updated", data))

    async def send_policy_updated(self, data: dict) -> None:
        self.events.append(("policy_updated", data))


class DummyDB(Database):
    async def insert_strategy(self, strategy_id: str, meta: dict | None) -> None:  # pragma: no cover - not used
        raise NotImplementedError

    async def set_status(self, strategy_id: str, status: str) -> None:  # pragma: no cover - not used
        raise NotImplementedError

    async def get_status(self, strategy_id: str) -> str | None:  # pragma: no cover - not used
        return None

    async def append_event(self, strategy_id: str, event: str) -> None:  # pragma: no cover - not used
        raise NotImplementedError


@pytest.mark.asyncio
async def test_consumer_relays_and_deduplicates():
    metrics.reset_metrics()
    hub = FakeHub()
    consumer = ControlBusConsumer(brokers=[], topics=["activation", "policy"], group="g", ws_hub=hub)
    await consumer.start()
    ts = time.time() * 1000
    msg1 = ControlBusMessage(topic="activation", key="a", etag="e1", run_id="r1", data={"id": 1}, timestamp_ms=ts)
    dup = ControlBusMessage(topic="activation", key="a", etag="e1", run_id="r1", data={"id": 1}, timestamp_ms=ts)
    msg2 = ControlBusMessage(topic="policy", key="a", etag="e2", run_id="r2", data={"id": 2}, timestamp_ms=ts)
    await consumer.publish(msg1)
    await consumer.publish(dup)
    await consumer.publish(msg2)
    await asyncio.sleep(0.1)
    await consumer.stop()
    assert hub.events == [
        ("activation_updated", {"id": 1}),
        ("policy_updated", {"id": 2}),
    ]
    assert metrics.event_relay_events_total.labels(topic="activation")._value.get() == 1
    assert metrics.event_relay_events_total.labels(topic="policy")._value.get() == 1
    assert metrics.event_relay_dropped_total.labels(topic="activation")._value.get() == 1


class StartStopConsumer(ControlBusConsumer):
    def __init__(self):
        super().__init__(brokers=[], topics=[], group="g")
        self.started = False
        self.stopped = False

    async def start(self) -> None:  # type: ignore[override]
        self.started = True

    async def stop(self) -> None:  # type: ignore[override]
        self.stopped = True


@pytest.mark.asyncio
async def test_app_starts_and_stops_consumer(fake_redis):
    hub = FakeHub()
    consumer = StartStopConsumer()
    app = create_app(
        redis_client=fake_redis,
        database=DummyDB(),
        ws_hub=hub,
        controlbus_consumer=consumer,
    )
    async with app.router.lifespan_context(app):
        assert consumer.started
    assert consumer.stopped
