import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from qmtl.foundation.common.metrics_factory import get_metric_value
from qmtl.services.worldservice import metrics as ws_metrics
from qmtl.services.worldservice.extended_validation_worker import ExtendedValidationWorker
from qmtl.services.worldservice.policy_engine import parse_policy
from qmtl.services.worldservice.storage import Storage
from qmtl.services.worldservice.validation_controlbus_consumer import ValidationControlBusConsumer


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

    async def start(self) -> None:
        return

    async def stop(self) -> None:
        return

    async def send_and_wait(self, topic: str, data: bytes, key: bytes | None = None) -> None:
        self.sent.append((topic, data, key))


@pytest.mark.asyncio
async def test_validation_consumer_triggers_extended_worker_for_event():
    ws_metrics.reset_metrics()
    storage = Storage()
    await storage.create_world({"id": "w", "name": "W"})
    policy = parse_policy(
        {
            "cohort": {"top_k": 1, "sharpe_median_min": 0.9, "severity": "soft"},
            "portfolio": {"max_incremental_var_99": 0.5, "severity": "soft"},
            "stress": {"scenarios": {"crash": {"dd_max": 0.3}}},
            "live_monitoring": {"sharpe_min": 0.6, "dd_max": 0.4, "severity": "soft"},
        }
    )
    version = await storage.add_policy("w", policy)
    await storage.set_default_policy("w", version=version)

    await storage.record_evaluation_run(
        "w",
        "s1",
        "run-1",
        stage="backtest",
        risk_tier="medium",
        metrics={
            "returns": {"sharpe": 1.1},
            "risk": {"incremental_var_99": 0.4},
            "stress": {"crash": {"max_drawdown": 0.2}},
            "diagnostics": {"live_sharpe": 0.95, "live_max_drawdown": 0.15},
        },
        validation={},
        summary={"status": "pass"},
    )

    async def _on_event(event) -> None:
        worker = ExtendedValidationWorker(storage)
        await worker.run(
            event.world_id,
            stage=event.stage,
            policy_payload=None,
            strategy_id=event.strategy_id,
            run_id=event.run_id,
        )

    payload = {
        "type": "evaluation_run_created",
        "time": datetime.now(timezone.utc).isoformat(),
        "data": {
            "world_id": "w",
            "strategy_id": "s1",
            "run_id": "run-1",
            "stage": "backtest",
            "version": 1,
            "idempotency_key": "evaluation_run_created:w:s1:run-1:1",
        },
    }
    consumer = _StubKafkaConsumer([SimpleNamespace(value=json.dumps(payload))])

    worker = ValidationControlBusConsumer(on_event=_on_event, consumer=consumer)
    await worker.start()
    await asyncio.sleep(0.05)
    await worker.stop()

    record = await storage.get_evaluation_run("w", "s1", "run-1")
    assert record is not None
    assert record["validation"].get("extended_revision") == 1


@pytest.mark.asyncio
async def test_validation_consumer_dedupes_by_idempotency_key():
    ws_metrics.reset_metrics()
    called = 0

    async def _on_event(_event) -> None:
        nonlocal called
        called += 1

    evt = {
        "type": "evaluation_run_created",
        "time": datetime.now(timezone.utc).isoformat(),
        "data": {
            "world_id": "w",
            "strategy_id": "s1",
            "run_id": "r1",
            "stage": "paper",
            "idempotency_key": "k1",
        },
    }
    consumer = _StubKafkaConsumer([SimpleNamespace(value=json.dumps(evt)), SimpleNamespace(value=json.dumps(evt))])
    worker = ValidationControlBusConsumer(on_event=_on_event, consumer=consumer)

    await worker.start()
    await asyncio.sleep(0.05)
    await worker.stop()

    assert called == 1
    assert (
        get_metric_value(
            ws_metrics.validation_event_dedupe_total,
            {"world_id": "w", "event_type": "evaluation_run_created", "stage": "paper"},
        )
        == 1
    )


@pytest.mark.asyncio
async def test_validation_consumer_skips_expired_event():
    ws_metrics.reset_metrics()
    called = 0

    async def _on_event(_event) -> None:
        nonlocal called
        called += 1

    old_time = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    evt = {
        "type": "evaluation_run_created",
        "time": old_time,
        "data": {
            "world_id": "w",
            "strategy_id": "s1",
            "run_id": "r1",
            "stage": "paper",
            "idempotency_key": "k1",
        },
    }
    consumer = _StubKafkaConsumer([SimpleNamespace(value=json.dumps(evt))])
    worker = ValidationControlBusConsumer(on_event=_on_event, consumer=consumer, event_ttl_sec=1)

    await worker.start()
    await asyncio.sleep(0.05)
    await worker.stop()

    assert called == 0
    assert (
        get_metric_value(
            ws_metrics.validation_event_expired_total,
            {"world_id": "w", "event_type": "evaluation_run_created", "stage": "paper"},
        )
        == 1
    )


@pytest.mark.asyncio
async def test_validation_consumer_retries_then_succeeds():
    ws_metrics.reset_metrics()
    calls = 0

    async def _on_event(_event) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")

    evt = {
        "type": "evaluation_run_created",
        "time": datetime.now(timezone.utc).isoformat(),
        "data": {
            "world_id": "w",
            "strategy_id": "s1",
            "run_id": "r1",
            "stage": "paper",
            "idempotency_key": "k1",
        },
    }
    consumer = _StubKafkaConsumer([SimpleNamespace(value=json.dumps(evt))])
    dlq = _StubKafkaProducer()
    worker = ValidationControlBusConsumer(
        on_event=_on_event,
        consumer=consumer,
        max_attempts=2,
        retry_backoff_sec=0.0,
        dlq_topic="dlq",
        dlq_producer=dlq,
    )

    await worker.start()
    await asyncio.sleep(0.05)
    await worker.stop()

    assert calls == 2
    assert not dlq.sent
    assert (
        get_metric_value(
            ws_metrics.validation_event_retry_total,
            {"world_id": "w", "event_type": "evaluation_run_created", "stage": "paper"},
        )
        == 1
    )
    assert (
        get_metric_value(
            ws_metrics.validation_event_processed_total,
            {"world_id": "w", "event_type": "evaluation_run_created", "stage": "paper"},
        )
        == 1
    )


@pytest.mark.asyncio
async def test_validation_consumer_sends_dlq_after_retries_exhausted():
    ws_metrics.reset_metrics()

    async def _on_event(_event) -> None:
        raise RuntimeError("boom")

    evt = {
        "type": "evaluation_run_created",
        "time": datetime.now(timezone.utc).isoformat(),
        "data": {
            "world_id": "w",
            "strategy_id": "s1",
            "run_id": "r1",
            "stage": "paper",
            "idempotency_key": "k1",
        },
    }
    consumer = _StubKafkaConsumer([SimpleNamespace(value=json.dumps(evt))])
    dlq = _StubKafkaProducer()
    worker = ValidationControlBusConsumer(
        on_event=_on_event,
        consumer=consumer,
        max_attempts=2,
        retry_backoff_sec=0.0,
        dlq_topic="dlq",
        dlq_producer=dlq,
    )

    await worker.start()
    await asyncio.sleep(0.05)
    await worker.stop()

    assert len(dlq.sent) == 1
    topic, raw, key = dlq.sent[0]
    assert topic == "dlq"
    assert key == b"w"
    payload = json.loads(raw.decode())
    assert payload["type"] == "validation_event_dlq"
    assert payload["data"]["event_type"] == "evaluation_run_created"
    assert payload["data"]["attempts"] == 2

    assert (
        get_metric_value(
            ws_metrics.validation_event_failed_total,
            {"world_id": "w", "event_type": "evaluation_run_created", "stage": "paper"},
        )
        == 1
    )
    assert (
        get_metric_value(
            ws_metrics.validation_event_dlq_total,
            {"world_id": "w", "event_type": "evaluation_run_created", "stage": "paper"},
        )
        == 1
    )
