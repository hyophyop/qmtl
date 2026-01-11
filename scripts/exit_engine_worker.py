"""Background worker to apply exit engine decisions from risk snapshots."""

from __future__ import annotations

import asyncio
import os

from qmtl.services.exit_engine import (
    ExitEngineControlBusConsumer,
    WorldServiceActivationClient,
    load_exit_engine_config,
)


async def main() -> None:
    config = load_exit_engine_config(dict(os.environ))
    if not config.controlbus_brokers or not config.controlbus_topic:
        raise SystemExit("Missing CONTROLBUS_BROKERS/CONTROLBUS_TOPIC for exit engine")

    client = WorldServiceActivationClient(
        config.ws_base_url,
        timeout=config.request_timeout_sec,
        auth_header=config.auth_header,
        auth_token=config.auth_token,
    )
    consumer = ExitEngineControlBusConsumer(
        config=config,
        activation_client=client,
        brokers=config.controlbus_brokers,
        topic=config.controlbus_topic,
        group_id=config.controlbus_group_id,
    )
    await consumer.start()
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await consumer.stop()
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
