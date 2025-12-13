"""Background worker to run extended validations from EvaluationRun ControlBus events."""

from __future__ import annotations

import asyncio
import os

import redis.asyncio as redis

from qmtl.services.worldservice.extended_validation_worker import ExtendedValidationWorker
from qmtl.services.worldservice.metrics import monotonic_seconds, record_extended_validation_run
from qmtl.services.worldservice.risk_hub import RiskSignalHub
from qmtl.services.worldservice.storage import PersistentStorage
from qmtl.services.worldservice.validation_controlbus_consumer import (
    ValidationControlBusConsumer,
    ValidationEvent,
)


async def main() -> None:
    dsn = os.environ.get("WORLDS_DB_DSN")
    redis_dsn = os.environ.get("WORLDS_REDIS_DSN")
    brokers = [b for b in (os.environ.get("CONTROLBUS_BROKERS") or "").split(",") if b]
    topic = os.environ.get("CONTROLBUS_TOPIC")
    group_id = os.environ.get("CONTROLBUS_GROUP_ID") or "worldservice-validation"
    dlq_topic = os.environ.get("CONTROLBUS_DLQ_TOPIC")
    max_attempts = int(os.environ.get("CONTROLBUS_MAX_ATTEMPTS") or "3")
    retry_backoff = float(os.environ.get("CONTROLBUS_RETRY_BACKOFF") or "0.5")
    dedupe_ttl = os.environ.get("CONTROLBUS_DEDUPE_TTL_SEC")
    event_ttl = os.environ.get("CONTROLBUS_EVENT_TTL_SEC")

    if not dsn or not redis_dsn or not brokers or not topic:
        raise SystemExit("Missing WORLDS_DB_DSN/WORLDS_REDIS_DSN/CONTROLBUS_BROKERS/CONTROLBUS_TOPIC")

    redis_client = redis.from_url(redis_dsn, decode_responses=True)
    storage = await PersistentStorage.create(db_dsn=dsn, redis_client=redis_client)

    hub = RiskSignalHub(repository=storage.risk_snapshots)
    hub.bind_cache(getattr(storage, "_redis", None))

    async def _on_event(event: ValidationEvent) -> None:
        if event.event_type == "evaluation_run_updated" and event.change_type == "extended_validation":
            return

        stage = event.stage
        if event.event_type == "validation_profile_changed":
            stage = None

        worker = ExtendedValidationWorker(storage, risk_hub=hub)
        started = monotonic_seconds()
        try:
            updated = await worker.run(
                event.world_id,
                stage=stage,
                policy_payload=None,
                strategy_id=event.strategy_id,
                run_id=event.run_id,
            )
        except Exception:
            record_extended_validation_run(
                event.world_id,
                stage=stage,
                status="failure",
                latency_seconds=monotonic_seconds() - started,
            )
            raise
        record_extended_validation_run(
            event.world_id,
            stage=stage,
            status="success" if updated else "no_updates",
            latency_seconds=monotonic_seconds() - started,
        )

    consumer = ValidationControlBusConsumer(
        brokers=brokers,
        topic=topic,
        group_id=group_id,
        dlq_topic=dlq_topic,
        max_attempts=max_attempts,
        retry_backoff_sec=retry_backoff,
        dedupe_cache=getattr(storage, "_redis", None),
        dedupe_ttl_sec=int(dedupe_ttl) if dedupe_ttl else None,
        event_ttl_sec=int(event_ttl) if event_ttl else None,
        on_event=_on_event,
    )

    await consumer.start()
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await consumer.stop()
        await storage.close()
        try:
            await redis_client.aclose()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
