from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from typing import Iterable

import uvicorn

from .grpc_server import serve
from .api import create_app
from .gc import GarbageCollector, QueueInfo, MetricsProvider, QueueStore
from .diff_service import StreamSender


class _NullStream(StreamSender):
    def send(self, chunk) -> None:  # pragma: no cover - simple no-op
        pass

    def wait_for_ack(self) -> None:  # pragma: no cover - noop
        pass

    def ack(self) -> None:  # pragma: no cover - noop
        pass


class _EmptyStore(QueueStore):
    def list_orphan_queues(self) -> Iterable[QueueInfo]:  # pragma: no cover - noop
        return []

    def drop_queue(self, name: str) -> None:  # pragma: no cover - noop
        pass


class _EmptyMetrics(MetricsProvider):
    def messages_in_per_sec(self) -> float:  # pragma: no cover - noop
        return 0.0


@dataclass
class _KafkaAdminClient:
    """Minimal AdminClient placeholder."""

    bootstrap_servers: str

    def list_topics(self):  # pragma: no cover - noop
        return {}

    def create_topic(self, name: str, *, num_partitions: int, replication_factor: int, config=None):
        pass  # pragma: no cover - noop


async def _run(args: argparse.Namespace) -> None:
    from neo4j import GraphDatabase  # pragma: no cover - external dependency

    driver = GraphDatabase.driver(args.neo4j_uri, auth=(args.neo4j_user, args.neo4j_password))
    admin = _KafkaAdminClient(args.kafka_bootstrap)

    gc = GarbageCollector(_EmptyStore(), _EmptyMetrics())

    grpc_server, _ = serve(
        driver,
        admin,
        _NullStream(),
        host=args.grpc_host,
        port=args.grpc_port,
        callback_url=args.diff_callback,
        gc=gc,
    )
    await grpc_server.start()

    app = create_app(gc, callback_url=args.gc_callback, driver=driver)
    config = uvicorn.Config(app, host=args.http_host, port=args.http_port, loop="asyncio", log_level="info")
    http_server = uvicorn.Server(config)

    await asyncio.gather(http_server.serve(), grpc_server.wait_for_termination())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="qmtl-dagmgr-server", description="Run DAG manager gRPC and HTTP servers")
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", default="neo4j")
    parser.add_argument("--kafka-bootstrap", default="localhost:9092")
    parser.add_argument("--grpc-host", default="0.0.0.0")
    parser.add_argument("--grpc-port", type=int, default=50051)
    parser.add_argument("--http-host", default="0.0.0.0")
    parser.add_argument("--http-port", type=int, default=8000)
    parser.add_argument("--diff-callback")
    parser.add_argument("--gc-callback")
    args = parser.parse_args(argv)

    asyncio.run(_run(args))


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
