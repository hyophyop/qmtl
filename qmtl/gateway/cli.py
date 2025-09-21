from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Any

import redis.asyncio as redis

from .redis_client import InMemoryRedis

from .api import create_app
from .config import GatewayConfig
from ..config import load_config, find_config_file
from .controlbus_consumer import ControlBusConsumer
from .commit_log import create_commit_log_writer
from .commit_log_consumer import CommitLogConsumer

try:  # pragma: no cover - aiokafka optional
    from aiokafka import AIOKafkaConsumer
except Exception:  # pragma: no cover - import guard
    AIOKafkaConsumer = Any  # type: ignore[misc]


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
    parser.add_argument(
        "--allow-live",
        dest="enforce_live_guard",
        action="store_false",
        help="Disable live trading guard requiring X-Allow-Live header",
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
    enforce_live_guard = (
        config.enforce_live_guard
        if args.enforce_live_guard is None
        else args.enforce_live_guard
    )
    consumer = None
    if config.controlbus_topics:
        consumer = ControlBusConsumer(
            brokers=config.controlbus_brokers,
            topics=config.controlbus_topics,
            group=config.controlbus_group,
        )

    commit_consumer = None
    commit_writer = None
    if config.commitlog_bootstrap and config.commitlog_topic:
        commit_writer = await create_commit_log_writer(
            config.commitlog_bootstrap,
            config.commitlog_topic,
            config.commitlog_transactional_id,
        )
        kafka_consumer = AIOKafkaConsumer(
            config.commitlog_topic,
            bootstrap_servers=config.commitlog_bootstrap,
            group_id=config.commitlog_group,
            enable_auto_commit=False,
        )
        commit_consumer = CommitLogConsumer(
            kafka_consumer,
            topic=config.commitlog_topic,
            group_id=config.commitlog_group,
        )

    async def _process_commits(records):
        for rec in records:
            logging.info("commit %s", rec)

    app = create_app(
        redis_client=redis_client,
        database_backend=config.database_backend,
        database_dsn=config.database_dsn,
        insert_sentinel=insert_sentinel,
        controlbus_consumer=consumer,
        commit_log_consumer=commit_consumer,
        commit_log_writer=commit_writer,
        commit_log_handler=_process_commits,
        worldservice_url=config.worldservice_url,
        worldservice_timeout=config.worldservice_timeout,
        worldservice_retries=config.worldservice_retries,
        enable_worldservice_proxy=config.enable_worldservice_proxy,
        enforce_live_guard=enforce_live_guard,
        accept_legacy_nodeids=config.accept_legacy_nodeids,
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
