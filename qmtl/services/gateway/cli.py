from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import redis.asyncio as redis

from .redis_client import InMemoryRedis

from .api import create_app
from .config import GatewayConfig
from qmtl.foundation.config import find_config_file, load_config
from .controlbus_consumer import ControlBusConsumer
from .commit_log import create_commit_log_writer
from .commit_log_consumer import CommitLogConsumer


def _log_config_source(
    cfg_path: str | None,
    *,
    cli_override: str | None,
    env_override: str | None,
) -> None:
    if cli_override:
        logging.info("Gateway configuration loaded from %s (--config)", cli_override)
        return

    if env_override:
        env_candidate = Path(env_override)
        if not env_candidate.is_absolute():
            env_candidate = Path.cwd() / env_candidate

        if cfg_path and Path(cfg_path) == env_candidate:
            logging.info(
                "Gateway configuration loaded from %s (QMTL_CONFIG_FILE)",
                cfg_path,
            )
            return

        if cfg_path:
            logging.warning(
                "QMTL_CONFIG_FILE=%s was ignored because the file could not be read; "
                "using %s instead",
                env_override,
                cfg_path,
            )
        else:
            logging.error(
                "QMTL_CONFIG_FILE=%s did not resolve to a readable file; using built-in defaults",
                env_override,
            )
        return

    if cfg_path:
        logging.info("Gateway configuration loaded from %s", cfg_path)
    else:
        logging.info("Gateway configuration file not provided; using built-in defaults")


try:  # pragma: no cover - aiokafka optional
    from aiokafka import AIOKafkaConsumer
except Exception:  # pragma: no cover - import guard
    AIOKafkaConsumer = Any  # type: ignore[misc]


async def _main(argv: list[str] | None = None) -> None:
    """Run the Gateway HTTP server."""
    parser = argparse.ArgumentParser(prog="qmtl service gateway")
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

    env_override = os.getenv("QMTL_CONFIG_FILE")
    cfg_path = args.config or find_config_file()
    _log_config_source(cfg_path, cli_override=args.config, env_override=env_override)
    config = GatewayConfig()
    if cfg_path:
        unified = load_config(cfg_path)
        if "gateway" not in unified.present_sections:
            logging.error(
                "Gateway configuration file %s does not define the 'gateway' section.",
                cfg_path,
            )
            raise SystemExit(2)
        config = unified.gateway

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

    if not config.commitlog_bootstrap or not config.commitlog_topic:
        logging.warning(
            "Commit-log writer is disabled; production deployments must set "
            "commitlog_bootstrap and commitlog_topic to record gateway.ingest events."
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
