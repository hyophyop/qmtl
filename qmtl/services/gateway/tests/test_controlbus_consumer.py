from typing import Any

import pytest

from qmtl.foundation.common.tagquery import MatchMode
from qmtl.services.gateway import metrics as gw_metrics
from qmtl.services.gateway.controlbus_consumer import ControlBusConsumer, ControlBusMessage


class _FakeHub:
    def __init__(self) -> None:
        self.activations: list[dict[str, Any]] = []
        self.policies: list[dict[str, Any]] = []
        self.queue_updates: list[tuple[Any, ...]] = []
        self.tag_upserts: list[tuple[list[str], int, list[Any]]] = []

    async def send_activation_updated(self, data: dict[str, Any]) -> None:
        self.activations.append(data)

    async def send_policy_updated(self, data: dict[str, Any]) -> None:
        self.policies.append(data)

    async def send_queue_update(
        self,
        tags: list[str],
        interval: int,
        queues: list[Any],
        mode: MatchMode,
        *,
        world_id: str | None = None,
        execution_domain: str | None = None,
        etag: str | None = None,
        ts: str | None = None,
    ) -> None:
        self.queue_updates.append(
            (
                tags,
                interval,
                queues,
                mode,
                world_id,
                execution_domain,
                etag,
                ts,
            )
        )

    async def send_tagquery_upsert(
        self, tags: list[str], interval: int, queues: list[Any]
    ) -> None:
        self.tag_upserts.append((tags, interval, queues))


@pytest.mark.asyncio
async def test_process_generic_message_routes_and_deduplicates(monkeypatch: pytest.MonkeyPatch) -> None:
    hub = _FakeHub()
    consumer = ControlBusConsumer([], ["activation"], "group-a", ws_hub=hub)

    recorded: dict[str, list[Any]] = {"control": [], "dropped": []}

    monkeypatch.setattr(
        gw_metrics,
        "record_controlbus_message",
        lambda topic, ts: recorded["control"].append((topic, ts)),
    )
    monkeypatch.setattr(
        gw_metrics, "record_event_dropped", lambda topic: recorded["dropped"].append(topic)
    )

    msg = ControlBusMessage(
        topic="activation",
        key="k1",
        etag="e1",
        run_id="r1",
        data={"version": 1, "etag": "e1", "run_id": "r1"},
    )

    await consumer._process_generic_message(msg)

    assert hub.activations == [msg.data]
    assert recorded["control"] == [("activation", None)]

    await consumer._process_generic_message(msg)

    assert recorded["dropped"] == ["activation"]
    assert hub.activations == [msg.data]


@pytest.mark.asyncio
async def test_queue_update_emits_tagquery_once(monkeypatch: pytest.MonkeyPatch) -> None:
    hub = _FakeHub()
    consumer = ControlBusConsumer([], ["queue"], "group-a", ws_hub=hub)

    control_calls: list[tuple[str, Any]] = []
    monkeypatch.setattr(
        gw_metrics,
        "record_controlbus_message",
        lambda topic, ts: control_calls.append((topic, ts)),
    )

    msg = ControlBusMessage(
        topic="queue",
        key="k1",
        etag="etag-1",
        run_id="run-1",
        data={
            "version": 1,
            "tags": ["t1"],
            "interval": 15,
            "queues": [{"queue": "alpha", "global": True}],
            "match_mode": "any",
            "etag": "etag-1",
            "ts": "1",
            "world_id": "w1",
            "execution_domain": "exe",
        },
    )

    await consumer._process_generic_message(msg)

    assert len(hub.queue_updates) == 1
    update = hub.queue_updates[0]
    assert update[0] == ["t1"]
    assert update[1] == 15
    assert update[3] == MatchMode.ANY
    assert hub.tag_upserts == [(["t1"], 15, [{"queue": "alpha", "global": True}])]

    msg2 = ControlBusMessage(
        topic="queue",
        key="k1",
        etag="etag-2",
        run_id="run-2",
        data={
            "version": 1,
            "tags": ["t1"],
            "interval": 15,
            "queues": [{"queue": "alpha", "global": True}],
            "match_mode": "any",
            "etag": "etag-2",
            "ts": "2",
            "world_id": "w1",
            "execution_domain": "exe",
        },
    )

    await consumer._process_generic_message(msg2)

    assert len(hub.queue_updates) == 2
    assert hub.tag_upserts == [(["t1"], 15, [{"queue": "alpha", "global": True}])]
    assert control_calls == [("queue", None), ("queue", None)]


@pytest.mark.asyncio
async def test_rebalancing_validation_error_logged(caplog: pytest.LogCaptureFixture) -> None:
    consumer = ControlBusConsumer([], ["rebalancing_planned"], "group-a", ws_hub=None)
    caplog.set_level("WARNING")

    msg = ControlBusMessage(
        topic="rebalancing_planned",
        key="k1",
        etag="e1",
        run_id="r1",
        data={"bad": "payload"},
    )

    await consumer._process_rebalancing_planned(msg)

    assert any("invalid rebalancing_planned payload" in rec.message for rec in caplog.records)
