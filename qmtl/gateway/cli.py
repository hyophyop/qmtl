from __future__ import annotations

import argparse
import asyncio
import logging

import redis.asyncio as redis

from .redis_client import InMemoryRedis

from .api import create_app
from .config import GatewayConfig
from ..config import load_config, find_config_file
from .controlbus_consumer import ControlBusConsumer


async def _main(argv: list[str] | None = None) -> None:
    """Run the Gateway HTTP server."""
    parser = argparse.ArgumentParser(prog="qmtl gw")
    parser.add_argument("--config", help="Path to configuration file")
    parser.add_argument(
        "--no-sentinel",
        dest="insert_sentinel",
        action="store_false",
        help="Disable automatic VersionSentinel insertion",
        default=None,
    )
    args = parser.parse_args(argv)

    cfg_path = args.config or find_config_file()
    config = GatewayConfig()
    if cfg_path:
        config = load_config(cfg_path).gateway

    if config.redis_dsn:
        redis_client = redis.from_url(config.redis_dsn, decode_responses=True)
    else:
        redis_client = InMemoryRedis()
    insert_sentinel = (
        config.insert_sentinel
        if args.insert_sentinel is None
        else args.insert_sentinel
    )
    consumer = None
    if config.controlbus_topics:
        consumer = ControlBusConsumer(
            brokers=config.controlbus_brokers,
            topics=config.controlbus_topics,
            group=config.controlbus_group,
        )

    app = create_app(
        redis_client=redis_client,
        database_backend=config.database_backend,
        database_dsn=config.database_dsn,
        insert_sentinel=insert_sentinel,
        controlbus_consumer=consumer,
        worldservice_url=config.worldservice_url,
        worldservice_timeout=config.worldservice_timeout,
        worldservice_retries=config.worldservice_retries,
        worldservice_breaker_max_failures=config.worldservice_breaker_max_failures,
        enable_worldservice_proxy=config.enable_worldservice_proxy,
        enforce_live_guard=config.enforce_live_guard,
    )
    db = app.state.database
    if hasattr(db, "connect"):
        try:
            await db.connect()  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - exception path tested separately
            logging.exception("Failed to connect to database")
            raise SystemExit("Failed to connect to database") from exc

    import uvicorn

    try:
        uvicorn.run(app, host=config.host, port=config.port)
    finally:
        if hasattr(db, "close"):
            try:
                await db.close()  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover - exception path tested separately
                logging.exception("Failed to close database connection")


def main(argv: list[str] | None = None) -> None:
    asyncio.run(_main(argv))


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
