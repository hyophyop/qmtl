from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Any

import redis.asyncio as redis

from .redis_client import InMemoryRedis

from .api import create_app
from .config import GatewayConfig
from .ws import WebSocketHub
from qmtl.foundation.common.tracing import setup_tracing
from qmtl.foundation.config import find_config_file, load_config
from qmtl.services.dagmanager.topic import set_topic_namespace_enabled
from .controlbus_consumer import ControlBusConsumer
from .commit_log import create_commit_log_writer
from .commit_log_consumer import CommitLogConsumer
from qmtl.utils.i18n import _, language_source, set_language


def _log_config_source(
    cfg_path: str | None,
    *,
    cli_override: str | None,
) -> None:
    if cli_override:
        logging.info(
            _("Gateway configuration loaded from %(path)s (--config)"),
            {"path": cli_override},
        )
        return

    if cfg_path:
        logging.info(
            _("Gateway configuration loaded from %(path)s"),
            {"path": cfg_path},
        )
    else:
        logging.info(
            _("Gateway configuration file not provided; using built-in defaults")
        )


try:  # pragma: no cover - aiokafka optional
    from aiokafka import AIOKafkaConsumer
except Exception:  # pragma: no cover - import guard
    AIOKafkaConsumer = Any  # type: ignore[misc]


async def _main(argv: list[str] | None = None) -> None:
    """Run the Gateway HTTP server."""
    if language_source() != "explicit":
        set_language(None)

    parser = argparse.ArgumentParser(
        prog="qmtl service gateway",
        description=_("Run the Gateway HTTP server."),
    )
    parser.add_argument("--config", help=_("Path to configuration file"))
    parser.add_argument(
        "--no-sentinel",
        dest="insert_sentinel",
        action="store_false",
        help=_("Disable automatic VersionSentinel insertion"),
        default=None,
    )
    parser.add_argument(
        "--allow-live",
        dest="enforce_live_guard",
        action="store_false",
        help=_("Disable live trading guard requiring X-Allow-Live header"),
        default=None,
    )
    args = parser.parse_args(argv)

    cfg_path = args.config or find_config_file()
    _log_config_source(cfg_path, cli_override=args.config)
    config = GatewayConfig()
    telemetry_enabled: bool | None = None
    telemetry_endpoint: str | None = None
    namespace_toggle: bool | None = None
    if cfg_path:
        unified = load_config(cfg_path)
        if "gateway" not in unified.present_sections:
            message = _(
                "Gateway configuration file {path} does not define the 'gateway' section."
            ).format(path=cfg_path)
            logging.error(message)
            parser.error(message)
        config = unified.gateway
        telemetry_enabled = unified.telemetry.enable_fastapi_otel
        telemetry_endpoint = unified.telemetry.otel_exporter_endpoint
        namespace_toggle = unified.dagmanager.enable_topic_namespace

    setup_tracing(
        "gateway",
        exporter_endpoint=telemetry_endpoint,
        config_path=cfg_path,
    )

    if namespace_toggle is not None:
        set_topic_namespace_enabled(namespace_toggle)

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
            _(
                "Commit-log writer is disabled; production deployments must set "
                "commitlog_bootstrap and commitlog_topic to record gateway.ingest events."
            )
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

    ws_hub = WebSocketHub(
        rate_limit_per_sec=config.websocket.rate_limit_per_sec,
    )
    event_descriptor = config.events.build_descriptor(
        logger=logging.getLogger(__name__)
    )

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
        ws_hub=ws_hub,
        event_config=event_descriptor,
        enable_otel=telemetry_enabled,
        shared_account_policy_config=config.shared_account_policy,
        health_capabilities=config.build_health_capabilities(),
    )
    db = app.state.database
    if hasattr(db, "connect"):
        try:
            await db.connect()  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - exception path tested separately
            message = _("Failed to connect to database")
            logging.exception(message)
            raise SystemExit(message) from exc

    import uvicorn

    try:
        uvicorn.run(app, host=config.host, port=config.port)
    finally:
        if hasattr(db, "close"):
            try:
                await db.close()  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover - exception path tested separately
                logging.exception(_("Failed to close database connection"))


def main(argv: list[str] | None = None) -> None:
    asyncio.run(_main(argv))


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
