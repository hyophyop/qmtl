import asyncio
import time
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi import FastAPI

from tests.helpers.metrics import mapping_store
from qmtl.services.gateway.controlbus_consumer import ControlBusConsumer, ControlBusMessage
from qmtl.services.gateway.api import Database
from qmtl.services.gateway import metrics
from qmtl.foundation.common.tagquery import MatchMode


class FakeHub:
    def __init__(self, done: asyncio.Event | None = None):
        self.events: list[tuple[str, dict]] = []
        self._done = done

    def _note_event(self) -> None:
        if self._done and len(self.events) >= 4:
            self._done.set()

    async def start(self) -> None:
        """Start method required by lifespan context."""
        pass

    async def stop(self) -> None:
        """Stop method required by lifespan context."""
        pass

    async def send_activation_updated(self, data: dict) -> None:
        self.events.append(("activation_updated", data))
        self._note_event()

    async def send_policy_updated(self, data: dict) -> None:
        self.events.append(("policy_updated", data))
        self._note_event()

    async def send_sentinel_weight(self, sentinel_id: str, weight: float) -> None:
        self.events.append(
            (
                "sentinel_weight",
                {"sentinel_id": sentinel_id, "weight": weight, "version": 1},
            )
        )
        self._note_event()

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
        self._note_event()

    async def send_tagquery_upsert(self, tags, interval, queues) -> None:
        self.events.append(
            (
                "tagquery.upsert",
                {"tags": tags, "interval": interval, "queues": queues, "version": 1},
            )
        )
        self._note_event()

    async def send_rebalancing_planned(
        self,
        *,
        world_id: str,
        plan: dict,
        version: int,
        policy: str | None = None,
        run_id: str | None = None,
        schema_version: int | None = None,
        alpha_metrics: dict | None = None,
        rebalance_intent: dict | None = None,
    ) -> None:
        payload = {"world_id": world_id, "plan": plan, "version": version}
        if policy:
            payload["policy"] = policy
        if run_id:
            payload["run_id"] = run_id
        if schema_version is not None:
            payload["schema_version"] = schema_version
        if alpha_metrics is not None:
            payload["alpha_metrics"] = alpha_metrics
        if rebalance_intent is not None:
            payload["rebalance_intent"] = rebalance_intent
        self.events.append(("rebalancing.planned", payload))
        self._note_event()


class RecordingPolicy:
    def __init__(self, *, allow: bool = True) -> None:
        self.allow = allow
        self.checked: list[Any] = []
        self.executed: list[Any] = []

    async def should_execute(self, event: Any) -> bool:
        self.checked.append(event)
        return self.allow

    async def execute(self, event: Any) -> None:
        self.executed.append(event)


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
    traffic_store = mapping_store(metrics.gateway_sentinel_traffic_ratio)
    assert traffic_store["v1"] == pytest.approx(0.75)
    assert "v1" in metrics._sentinel_weight_updates
    assert (
        metrics.event_relay_events_total.labels(topic="sentinel_weight")._value.get()
        == 1
    )


@pytest.mark.asyncio
async def test_rebalancing_plan_broadcasts_and_triggers_policy():
    metrics.reset_metrics()
    hub = FakeHub()
    policy = RecordingPolicy()
    consumer = ControlBusConsumer(
        brokers=[],
        topics=["rebalancing_planned"],
        group="g",
        ws_hub=hub,
        rebalancing_policy=policy,
    )
    await consumer.start()
    ts = time.time() * 1000
    plan_payload = {
        "world_id": "world-1",
        "plan": {
            "scale_world": 1.0,
            "scale_by_strategy": {"s1": 0.5},
            "deltas": [
                {"symbol": "BTC", "delta_qty": 1.25, "venue": "coinbase"},
                {"symbol": "ETH", "delta_qty": -0.5, "venue": None},
            ],
        },
        "version": 1,
        "policy": "auto",
        "run_id": "run-1",
    }
    msg = ControlBusMessage(
        topic="rebalancing_planned",
        key="world-1",
        etag="",
        run_id="",
        data=plan_payload,
        timestamp_ms=ts,
    )
    dup = ControlBusMessage(
        topic="rebalancing_planned",
        key="world-1",
        etag="",
        run_id="",
        data=plan_payload,
        timestamp_ms=ts,
    )

    await consumer.publish(msg)
    await consumer.publish(dup)
    await consumer._queue.join()
    await consumer.stop()

    assert hub.events == [
        (
            "rebalancing.planned",
            {
                "world_id": "world-1",
                "plan": plan_payload["plan"],
                "version": 1,
                "policy": "auto",
                "run_id": "run-1",
            },
        )
    ]
    assert len(policy.checked) == 1
    assert len(policy.executed) == 1
    assert (
        metrics.rebalance_plans_observed_total.labels(world_id="world-1")._value.get()
        == 1
    )
    assert (
        metrics.rebalance_plan_last_delta_count.labels(world_id="world-1")._value.get()
        == 2
    )
    assert (
        metrics.rebalance_plan_execution_attempts_total.labels(world_id="world-1")._value.get()
        == 1
    )
    assert (
        metrics.rebalance_plan_execution_failures_total.labels(world_id="world-1")._value.get()
        == 0
    )
    assert (
        metrics.event_relay_dropped_total.labels(topic="rebalancing_planned")._value.get()
        == 1
    )


@pytest.mark.asyncio
async def test_rebalancing_plan_broadcasts_v2_metadata():
    metrics.reset_metrics()
    hub = FakeHub()
    consumer = ControlBusConsumer(
        brokers=[],
        topics=["rebalancing_planned"],
        group="g",
        ws_hub=hub,
    )
    await consumer.start()
    ts = time.time() * 1000
    plan_payload = {
        "world_id": "world-2",
        "plan": {
            "scale_world": 0.9,
            "scale_by_strategy": {"s1": 0.5},
            "deltas": [{"symbol": "BTC", "delta_qty": 1.0, "venue": "coinbase"}],
        },
        "version": 2,
        "schema_version": 2,
        "alpha_metrics": {
            "per_world": {"world-2": {"alpha_performance.sharpe": 0.5}},
            "per_strategy": {},
        },
        "rebalance_intent": {"meta": {"ticket": "ws-1514"}},
    }
    msg = ControlBusMessage(
        topic="rebalancing_planned",
        key="world-2",
        etag="",
        run_id="",
        data=plan_payload,
        timestamp_ms=ts,
    )

    await consumer.publish(msg)
    await consumer._queue.join()
    await consumer.stop()

    assert hub.events == [
        (
            "rebalancing.planned",
            {
                "world_id": "world-2",
                "plan": plan_payload["plan"],
                "version": 2,
                "schema_version": 2,
                "alpha_metrics": plan_payload["alpha_metrics"],
                "rebalance_intent": plan_payload["rebalance_intent"],
            },
        )
    ]


class StartStopConsumer(ControlBusConsumer):
    def __init__(self):
        super().__init__(brokers=[], topics=[], group="g")
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
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
