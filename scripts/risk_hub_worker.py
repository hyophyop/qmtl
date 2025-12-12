"""Background worker to hydrate hub from ControlBus and trigger validations."""

from __future__ import annotations

import asyncio
import os

import redis.asyncio as redis

from qmtl.services.worldservice.api import create_app
from qmtl.services.worldservice.controlbus_consumer import RiskHubControlBusConsumer
from qmtl.services.worldservice.storage import PersistentStorage


async def main() -> None:
    dsn = os.environ.get("WORLDS_DB_DSN")
    redis_dsn = os.environ.get("WORLDS_REDIS_DSN")
    brokers = (os.environ.get("CONTROLBUS_BROKERS") or "").split(",")
    topic = os.environ.get("CONTROLBUS_TOPIC")
    group_id = os.environ.get("CONTROLBUS_GROUP_ID") or "worldservice-risk-hub"
    dlq_topic = os.environ.get("CONTROLBUS_DLQ_TOPIC")
    max_attempts = int(os.environ.get("CONTROLBUS_MAX_ATTEMPTS") or "3")
    retry_backoff = float(os.environ.get("CONTROLBUS_RETRY_BACKOFF") or "0.5")
    if not dsn or not redis_dsn or not brokers or not topic:
        raise SystemExit("Missing WORLDS_DB_DSN/WORLDS_REDIS_DSN/CONTROLBUS_BROKERS/CONTROLBUS_TOPIC")

    redis_client = redis.from_url(redis_dsn, decode_responses=True)
    storage = await PersistentStorage.create(db_dsn=dsn, redis_client=redis_client)
    app = create_app(storage=storage, profile="dev")  # storage injected, avoids config lookup
    hub = getattr(app.state, "world_service", app.state.world_service)._risk_hub  # type: ignore[attr-defined]

    consumer = RiskHubControlBusConsumer(
        hub=hub,
        brokers=[b for b in brokers if b],
        topic=topic,
        group_id=group_id,
        dlq_topic=dlq_topic,
        max_attempts=max_attempts,
        retry_backoff_sec=retry_backoff,
        on_snapshot=lambda snap: app.state.world_service._apply_extended_validation(  # type: ignore[attr-defined]
            world_id=snap.world_id,
            stage=None,
            policy_payload=None,
        ),
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
