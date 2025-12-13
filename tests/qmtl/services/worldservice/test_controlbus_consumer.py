import asyncio
import json
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import pytest

from qmtl.foundation.common.metrics_factory import get_metric_value
from qmtl.services.worldservice import metrics as ws_metrics
from qmtl.services.worldservice.controlbus_consumer import RiskHubControlBusConsumer
from qmtl.services.worldservice.risk_hub import RiskSignalHub, PortfolioSnapshot


class _StubKafkaConsumer:
    def __init__(self, messages):
        self._messages = messages
        self.started = False
        self.subscribed = False
        self.stopped = False

    async def start(self):
        self.started = True

    async def subscribe(self, _topics):
        self.subscribed = True

    def __aiter__(self):
        async def _gen():
            for m in self._messages:
                yield m
        return _gen()

    async def stop(self):
        self.stopped = True


class _StubKafkaProducer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes, bytes | None]] = []
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def send_and_wait(self, topic: str, data: bytes, key: bytes | None = None) -> None:
        self.sent.append((topic, data, key))


class _FlakyHub(RiskSignalHub):
    def __init__(self, *, fail_times: int = 0) -> None:
        super().__init__()
        self._fail_times = int(fail_times)
        self.calls = 0

    async def upsert_snapshot(self, snapshot: PortfolioSnapshot) -> None:  # type: ignore[override]
        self.calls += 1
        if self.calls <= self._fail_times:
            raise RuntimeError("boom")
        await super().upsert_snapshot(snapshot)


@pytest.mark.asyncio
async def test_controlbus_consumer_hydrates_hub_and_triggers_callback():
    hub = RiskSignalHub()
    called = asyncio.Event()

    async def _on_snapshot(snapshot: PortfolioSnapshot) -> None:
        called.set()

    data = {
        "type": "risk_snapshot_updated",
        "data": {
            "world_id": "w",
            "as_of": "2025-01-01T00:00:00Z",
            "version": "v1",
            "weights": {"a": 1.0},
            "provenance": {"actor": "gateway"},
        },
    }
    msg = SimpleNamespace(value=json.dumps(data))
    consumer = _StubKafkaConsumer([msg])

    worker = RiskHubControlBusConsumer(
        hub=hub,
        on_snapshot=_on_snapshot,
        consumer=consumer,
    )

    await worker.start()
    # allow loop to process the message
    await asyncio.sleep(0.05)
    await worker.stop()

    assert consumer.started
    assert consumer.stopped
    latest = await hub.latest_snapshot("w")
    assert latest is not None
    assert called.is_set()


@pytest.mark.asyncio
async def test_controlbus_consumer_dedupes_by_hash_and_actor():
    ws_metrics.reset_metrics()
    hub = RiskSignalHub()
    called = 0

    async def _on_snapshot(snapshot: PortfolioSnapshot) -> None:
        nonlocal called
        called += 1

    payload = {
        "world_id": "w",
        "as_of": "2025-01-01T00:00:00Z",
        "version": "v1",
        "weights": {"a": 1.0},
        "provenance": {"actor": "gateway", "stage": "paper"},
    }
    data = {"type": "risk_snapshot_updated", "data": payload}
    msg1 = SimpleNamespace(value=json.dumps(data))
    msg2 = SimpleNamespace(value=json.dumps(data))
    consumer = _StubKafkaConsumer([msg1, msg2])

    worker = RiskHubControlBusConsumer(
        hub=hub,
        on_snapshot=_on_snapshot,
        consumer=consumer,
    )

    await worker.start()
    await asyncio.sleep(0.05)
    await worker.stop()

    assert consumer.started
    assert consumer.stopped
    assert called == 1
    assert (
        get_metric_value(
            ws_metrics.risk_hub_snapshot_dedupe_total,
            {"world_id": "w", "stage": "paper"},
        )
        == 1
    )


@pytest.mark.asyncio
async def test_controlbus_consumer_skips_expired_snapshot():
    ws_metrics.reset_metrics()
    hub = RiskSignalHub()
    old_created = (
        datetime.now(timezone.utc) - timedelta(seconds=20)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    data = {
        "type": "risk_snapshot_updated",
        "data": {
            "world_id": "w",
            "as_of": "2025-01-01T00:00:00Z",
            "version": "v1",
            "weights": {"a": 1.0},
            "ttl_sec": 1,
            "created_at": old_created,
            "provenance": {"actor": "gateway"},
        },
    }
    msg = SimpleNamespace(value=json.dumps(data))
    consumer = _StubKafkaConsumer([msg])

    worker = RiskHubControlBusConsumer(
        hub=hub,
        consumer=consumer,
    )

    await worker.start()
    await asyncio.sleep(0.05)
    await worker.stop()

    assert await hub.latest_snapshot("w") is None
    assert (
        get_metric_value(
            ws_metrics.risk_hub_snapshot_expired_total,
            {"world_id": "w", "stage": "unknown"},
        )
        == 1
    )


@pytest.mark.asyncio
async def test_controlbus_consumer_retries_then_succeeds():
    ws_metrics.reset_metrics()
    hub = _FlakyHub(fail_times=1)
    dlq = _StubKafkaProducer()

    data = {
        "type": "risk_snapshot_updated",
        "data": {
            "world_id": "w",
            "as_of": "2025-01-01T00:00:00Z",
            "version": "v1",
            "weights": {"a": 1.0},
            "provenance": {"actor": "gateway", "stage": "paper"},
        },
    }
    msg = SimpleNamespace(value=json.dumps(data))
    consumer = _StubKafkaConsumer([msg])

    worker = RiskHubControlBusConsumer(
        hub=hub,
        consumer=consumer,
        max_attempts=2,
        retry_backoff_sec=0.0,
        dlq_topic="dlq",
        dlq_producer=dlq,
    )

    await worker.start()
    await asyncio.sleep(0.05)
    await worker.stop()

    assert hub.calls == 2
    assert not dlq.sent
    assert (
        get_metric_value(
            ws_metrics.risk_hub_snapshot_retry_total,
            {"world_id": "w", "stage": "paper"},
        )
        == 1
    )
    assert (
        get_metric_value(
            ws_metrics.risk_hub_snapshot_processed_total,
            {"world_id": "w", "stage": "paper"},
        )
        == 1
    )


@pytest.mark.asyncio
async def test_controlbus_consumer_derives_dlq_topic_from_controlbus_topic():
    ws_metrics.reset_metrics()
    hub = _FlakyHub(fail_times=10)
    dlq = _StubKafkaProducer()

    data = {
        "type": "risk_snapshot_updated",
        "data": {
            "world_id": "w",
            "as_of": "2025-01-01T00:00:00Z",
            "version": "v1",
            "weights": {"a": 1.0},
            "provenance": {"actor": "gateway", "stage": "paper"},
        },
    }
    msg = SimpleNamespace(value=json.dumps(data))
    consumer = _StubKafkaConsumer([msg])

    worker = RiskHubControlBusConsumer(
        hub=hub,
        consumer=consumer,
        max_attempts=1,
        retry_backoff_sec=0.0,
        dlq_producer=dlq,
        topic="controlbus",
    )

    assert worker._dlq_topic == "controlbus.dlq"

    await worker.start()
    await asyncio.sleep(0.05)
    await worker.stop()

    assert len(dlq.sent) == 1
    sent_topic, raw, key = dlq.sent[0]
    assert sent_topic == "controlbus.dlq"
    assert key == b"w"
    evt = json.loads(raw.decode())
    assert evt["type"] == "risk_snapshot_updated_dlq"
    assert evt["data"]["stage"] == "paper"
    assert (
        get_metric_value(
            ws_metrics.risk_hub_snapshot_failed_total,
            {"world_id": "w", "stage": "paper"},
        )
        == 1
    )
    assert (
        get_metric_value(
            ws_metrics.risk_hub_snapshot_dlq_total,
            {"world_id": "w", "stage": "paper"},
        )
        == 1
    )


@pytest.mark.asyncio
async def test_controlbus_consumer_sends_dlq_after_retries_exhausted():
    ws_metrics.reset_metrics()
    hub = _FlakyHub(fail_times=10)
    dlq = _StubKafkaProducer()

    data = {
        "type": "risk_snapshot_updated",
        "data": {
            "world_id": "w",
            "as_of": "2025-01-01T00:00:00Z",
            "version": "v1",
            "weights": {"a": 1.0},
            "provenance": {"actor": "gateway", "stage": "paper"},
        },
    }
    msg = SimpleNamespace(value=json.dumps(data))
    consumer = _StubKafkaConsumer([msg])

    worker = RiskHubControlBusConsumer(
        hub=hub,
        consumer=consumer,
        max_attempts=2,
        retry_backoff_sec=0.0,
        dlq_topic="dlq",
        dlq_producer=dlq,
    )

    await worker.start()
    await asyncio.sleep(0.05)
    await worker.stop()

    assert hub.calls == 2
    assert len(dlq.sent) == 1
    topic, raw, key = dlq.sent[0]
    assert topic == "dlq"
    assert key == b"w"
    evt = json.loads(raw.decode())
    assert evt["type"] == "risk_snapshot_updated_dlq"
    assert evt["data"]["world_id"] == "w"
    assert evt["data"]["stage"] == "paper"
    assert evt["data"]["attempts"] == 2
    assert (
        get_metric_value(
            ws_metrics.risk_hub_snapshot_retry_total,
            {"world_id": "w", "stage": "paper"},
        )
        == 1
    )
    assert (
        get_metric_value(
            ws_metrics.risk_hub_snapshot_failed_total,
            {"world_id": "w", "stage": "paper"},
        )
        == 1
    )
    assert (
        get_metric_value(
            ws_metrics.risk_hub_snapshot_dlq_total,
            {"world_id": "w", "stage": "paper"},
        )
        == 1
    )
