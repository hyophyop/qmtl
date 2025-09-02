from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from typing import Any

from . import metrics as gw_metrics
from .commit_log_consumer import CommitLogConsumer

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="qmtl-commitlog-consumer", description="Run CommitLog consumer")
    p.add_argument("--bootstrap", required=True, help="Kafka bootstrap servers, e.g. localhost:9092")
    p.add_argument("--topic", required=True, help="Commit log topic")
    p.add_argument("--group", required=True, help="Consumer group id")
    p.add_argument("--metrics-port", type=int, default=8000, help="Prometheus metrics port")
    p.add_argument("--poll-timeout-ms", type=int, default=500, help="Poll timeout in milliseconds")
    return p


async def _create_consumer(bootstrap: str, topic: str, group: str) -> Any:
    try:
        from aiokafka import AIOKafkaConsumer  # type: ignore
    except Exception as e:  # pragma: no cover - optional dependency
        raise RuntimeError("aiokafka is required to run the consumer") from e
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=bootstrap,
        group_id=group,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    return consumer


async def run(bootstrap: str, topic: str, group: str, poll_timeout_ms: int) -> None:
    consumer = await _create_consumer(bootstrap, topic, group)
    clc = CommitLogConsumer(consumer, topic=topic, group_id=group)

    async def processor(records):  # pragma: no cover - runtime path
        logger.info("processed %d records", len(records))

    stop_event = asyncio.Event()

    def _shutdown(*_: int) -> None:  # pragma: no cover - runtime path
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):  # pragma: no cover - runtime path
        loop.add_signal_handler(sig, _shutdown, sig)

    try:
        while not stop_event.is_set():  # pragma: no cover - runtime path
            await clc.consume(processor, timeout_ms=poll_timeout_ms)
            await asyncio.sleep(0.05)
    finally:
        try:
            await clc.stop()
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to stop consumer")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    args = build_parser().parse_args(argv)
    gw_metrics.start_metrics_server(port=args.metrics_port)
    asyncio.run(run(args.bootstrap, args.topic, args.group, args.poll_timeout_ms))
    return 0


__all__ = ["build_parser", "main", "run"]

