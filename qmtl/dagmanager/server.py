from __future__ import annotations
import argparse
import asyncio
from dataclasses import dataclass
from typing import Iterable

from qmtl.common import AsyncCircuitBreaker

import uvicorn

from .grpc_server import serve
from .config import DagManagerConfig
from ..config import load_config, find_config_file
from .api import create_app
from .gc import GarbageCollector, QueueInfo, MetricsProvider, QueueStore
from .diff_service import StreamSender
from .monitor import AckStatus


class _NullStream(StreamSender):
    def send(self, chunk) -> None:  # pragma: no cover - simple no-op
        pass

    def wait_for_ack(self) -> AckStatus:  # pragma: no cover - noop
        return AckStatus.OK

    def ack(self, status: AckStatus = AckStatus.OK) -> None:  # pragma: no cover - noop
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


async def _run(cfg: DagManagerConfig) -> None:
    driver = None
    repo = None
    admin_client = None
    queue = None

    if cfg.neo4j_dsn:
        from neo4j import GraphDatabase  # pragma: no cover - external dependency

        driver = GraphDatabase.driver(
            cfg.neo4j_dsn, auth=(cfg.neo4j_user, cfg.neo4j_password)
        )
        repo = None
    else:
        from .node_repository import MemoryNodeRepository

        repo = MemoryNodeRepository(cfg.memory_repo_path)

    if cfg.kafka_dsn:
        from .kafka_admin import KafkaAdmin
        from .diff_service import KafkaQueueManager

        admin_client = _KafkaAdminClient(cfg.kafka_dsn)
        # Manual reset of the breaker is expected after successful operations
        breaker = AsyncCircuitBreaker(
            max_failures=cfg.kafka_breaker_threshold,
        )
        queue = KafkaQueueManager(KafkaAdmin(admin_client, breaker=breaker))
    else:
        from .kafka_admin import InMemoryAdminClient, KafkaAdmin
        from .diff_service import KafkaQueueManager

        admin_client = InMemoryAdminClient()
        # Manual reset of the breaker is expected after successful operations
        breaker = AsyncCircuitBreaker(
            max_failures=cfg.kafka_breaker_threshold,
        )
        queue = KafkaQueueManager(KafkaAdmin(admin_client, breaker=breaker))

    gc = GarbageCollector(_EmptyStore(), _EmptyMetrics())

    grpc_server, _ = serve(
        driver,
        admin_client,
        _NullStream(),
        host=cfg.grpc_host,
        port=cfg.grpc_port,
        callback_url=cfg.diff_callback,
        gc=gc,
        repo=repo,
        queue=queue,
        breaker_threshold=cfg.kafka_breaker_threshold,
    )
    await grpc_server.start()

    app = create_app(gc, callback_url=cfg.gc_callback, driver=driver)
    config = uvicorn.Config(app, host=cfg.http_host, port=cfg.http_port, loop="asyncio", log_level="info")
    http_server = uvicorn.Server(config)

    await asyncio.gather(http_server.serve(), grpc_server.wait_for_termination())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="qmtl dagmanager-server", description="Run DAG manager gRPC and HTTP servers"
    )
    parser.add_argument("--config", help="Path to configuration file")
    args = parser.parse_args(argv)

    cfg_path = args.config or find_config_file()
    cfg = DagManagerConfig()
    if cfg_path:
        cfg = load_config(cfg_path).dagmanager

    asyncio.run(_run(cfg))


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
