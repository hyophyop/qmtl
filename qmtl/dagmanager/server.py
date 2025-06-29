from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from typing import Iterable

import uvicorn

from .grpc_server import serve
from .config import DagManagerConfig, load_dagmanager_config
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


async def _run(cfg: DagManagerConfig) -> None:
    driver = None
    repo = None
    admin_client = None
    queue = None

    if cfg.repo_backend == "neo4j":
        from neo4j import GraphDatabase  # pragma: no cover - external dependency

        driver = GraphDatabase.driver(
            cfg.neo4j_uri, auth=(cfg.neo4j_user, cfg.neo4j_password)
        )
        repo = None
    elif cfg.repo_backend == "memory":
        from .node_repository import MemoryNodeRepository

        repo = MemoryNodeRepository(cfg.memory_repo_path)
    if cfg.queue_backend == "kafka":
        admin_client = _KafkaAdminClient(cfg.kafka_bootstrap)
        queue = None
    elif cfg.queue_backend == "memory":
        from .kafka_admin import InMemoryAdminClient, KafkaAdmin
        from .diff_service import KafkaQueueManager

        admin_client = InMemoryAdminClient()
        queue = KafkaQueueManager(KafkaAdmin(admin_client))

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
    )
    await grpc_server.start()

    app = create_app(gc, callback_url=cfg.gc_callback, driver=driver)
    config = uvicorn.Config(app, host=cfg.http_host, port=cfg.http_port, loop="asyncio", log_level="info")
    http_server = uvicorn.Server(config)

    await asyncio.gather(http_server.serve(), grpc_server.wait_for_termination())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="qmtl dagmgr-server", description="Run DAG manager gRPC and HTTP servers"
    )
    parser.add_argument("--config", help="Path to configuration file")
    args = parser.parse_args(argv)

    cfg = DagManagerConfig()
    if args.config:
        cfg = load_dagmanager_config(args.config)

    asyncio.run(_run(cfg))


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
