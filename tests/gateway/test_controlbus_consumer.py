import asyncio
import time
from contextlib import asynccontextmanager
import pytest
from fastapi import FastAPI

from qmtl.gateway.controlbus_consumer import ControlBusConsumer, ControlBusMessage
from qmtl.gateway.api import Database
from qmtl.gateway import metrics
from qmtl.common.tagquery import MatchMode


class FakeHub:
    def __init__(self, done: asyncio.Event | None = None):
        self.events: list[tuple[str, dict]] = []
        self._done = done

    async def start(self) -> None:
        """Start method required by lifespan context."""
        pass

    async def stop(self) -> None:
        """Stop method required by lifespan context."""
        pass

    async def send_activation_updated(self, data: dict) -> None:
        self.events.append(("activation_updated", data))
        if self._done and len(self.events) == 4:
            self._done.set()

    async def send_policy_updated(self, data: dict) -> None:
        self.events.append(("policy_updated", data))
        if self._done and len(self.events) == 4:
            self._done.set()

    async def send_sentinel_weight(self, sentinel_id: str, weight: float) -> None:
        self.events.append(
            (
                "sentinel_weight",
                {"sentinel_id": sentinel_id, "weight": weight, "version": 1},
            )
        )
        if self._done and len(self.events) == 4:
            self._done.set()

    async def send_queue_update(
        self,
        tags,
        interval,
        queues,
        match_mode: MatchMode = MatchMode.ANY,
        *,
        etag: str | None = None,
        ts: str | None = None,
    ) -> None:
        self.events.append(
            (
                "queue_update",
                {
                    "tags": tags,
                    "interval": interval,
                    "queues": queues,
                    "match_mode": match_mode,
                    "etag": etag,
                    "ts": ts,
                    "version": 1,
                },
            )
        )
        if self._done and len(self.events) == 4:
            self._done.set()

    async def send_tagquery_upsert(self, tags, interval, queues) -> None:
        self.events.append(
            (
                "tagquery.upsert",
                {"tags": tags, "interval": interval, "queues": queues, "version": 1},
            )
        )
        if self._done and len(self.events) == 4:
            self._done.set()


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
    done = asyncio.Event()
    hub = FakeHub(done)
    consumer = ControlBusConsumer(
        brokers=[], topics=["activation", "policy", "queue"], group="g", ws_hub=hub
    )
    await consumer.start()
    ts = time.time() * 1000
    act_payload = {
        "id": 1,
        "version": 1,
        "etag": "e1",
        "run_id": "r1",
        "ts": "2024-01-01T00:00:00Z",
        "state_hash": "h1",
    }
    msg1 = ControlBusMessage(topic="activation", key="a", etag="e1", run_id="r1", data=act_payload, timestamp_ms=ts)
    dup = ControlBusMessage(topic="activation", key="a", etag="e1", run_id="r1", data=act_payload, timestamp_ms=ts)
    pol_payload = {
        "id": 2,
        "version": 1,
        "policy_version": 1,
        "checksum": "c1",
        "status": "ACTIVE",
        "ts": "2024-01-01T00:00:00Z",
    }
    msg2 = ControlBusMessage(topic="policy", key="a", etag="", run_id="", data=pol_payload, timestamp_ms=ts)
    msg3 = ControlBusMessage(
        topic="queue",
        key="t",
        etag="e3",
        run_id="r3",
        data={
            "tags": ["x"],
            "interval": 60,
            "queues": [{"queue": "q", "global": False}],
            "match_mode": "any",
            "version": 1,
            "etag": "e3",
            "ts": "2020-01-01T00:00:00Z",
        },
        timestamp_ms=ts,
    )
    await consumer.publish(msg1)
    await consumer.publish(dup)
    await consumer.publish(msg2)
    await consumer.publish(msg3)
    await consumer._queue.join()
    await consumer.stop()
    assert hub.events == [
        ("activation_updated", act_payload),
        ("policy_updated", pol_payload),
        (
            "queue_update",
            {
                "tags": ["x"],
                "interval": 60,
                "queues": [{"queue": "q", "global": False}],
                "match_mode": MatchMode.ANY,
                "etag": "e3",
                "ts": "2020-01-01T00:00:00Z",
                "version": 1,
            },
        ),
        (
            "tagquery.upsert",
            {
                "tags": ["x"],
                "interval": 60,
                "queues": [{"queue": "q", "global": False}],
                "version": 1,
            },
        ),
    ]
    assert metrics.event_relay_events_total.labels(topic="activation")._value.get() == 1
    assert metrics.event_relay_events_total.labels(topic="policy")._value.get() == 1
    assert metrics.event_relay_events_total.labels(topic="queue")._value.get() == 1
    assert metrics.event_relay_dropped_total.labels(topic="activation")._value.get() == 1


@pytest.mark.asyncio
async def test_sentinel_weight_updates_metrics_and_ws():
    metrics.reset_metrics()
    hub = FakeHub()
    consumer = ControlBusConsumer(
        brokers=[], topics=["sentinel_weight"], group="g", ws_hub=hub
    )
    await consumer.start()
    msg = ControlBusMessage(
        topic="sentinel_weight",
        key="sentinel:v1",
        etag="",
        run_id="",
        data={"sentinel_id": "v1", "weight": 0.75, "version": 1},
        timestamp_ms=time.time() * 1000,
    )
    await consumer.publish(msg)
    await consumer._queue.join()
    await consumer.stop()

    assert hub.events == [
        ("sentinel_weight", {"sentinel_id": "v1", "weight": 0.75, "version": 1})
    ]
    assert metrics.gateway_sentinel_traffic_ratio._vals["v1"] == pytest.approx(0.75)
    assert "v1" in metrics._sentinel_weight_updates
    assert (
        metrics.event_relay_events_total.labels(topic="sentinel_weight")._value.get()
        == 1
    )


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
    consumer = StartStopConsumer()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await consumer.start()
        yield
        await consumer.stop()

    app = FastAPI(lifespan=lifespan)
    async with app.router.lifespan_context(app):
        assert consumer.started
    assert consumer.stopped
