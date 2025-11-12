from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import sys
from dataclasses import dataclass, field
from typing import Mapping, Sequence

import uvicorn

from qmtl.foundation.common import AsyncCircuitBreaker
from qmtl.foundation.common.tracing import setup_tracing
from qmtl.foundation.config import find_config_file, load_config
from qmtl.utils.i18n import _, set_language


def _log_config_source(
    cfg_path: str | None,
    *,
    cli_override: str | None,
) -> None:
    if cli_override:
        logging.info(
            _("DAG Manager configuration loaded from %s (--config)"), cli_override
        )
        return

    if cfg_path:
        logging.info(_("DAG Manager configuration loaded from %s"), cfg_path)
    else:
        logging.info(
            _("DAG Manager configuration file not provided; using built-in defaults")
        )


from .api import create_app
from .garbage_collector import GarbageCollector, MetricsProvider, QueueStore
from .diff_service import StreamSender
from .monitor import AckStatus
from .controlbus_producer import ControlBusProducer
from .queue_store import KafkaQueueStore
from .metrics_provider import KafkaMetricsProvider
from .gc_scheduler import GCScheduler


class _NullStream(StreamSender):
    def send(self, chunk) -> None:  # pragma: no cover - simple no-op
        pass

    def wait_for_ack(self) -> AckStatus:  # pragma: no cover - noop
        return AckStatus.OK

    def ack(self, status: AckStatus = AckStatus.OK) -> None:  # pragma: no cover - noop
        pass


@dataclass
class _KafkaAdminClient:
    """Thin wrapper around :mod:`confluent_kafka` for metadata access."""

    bootstrap_servers: str
    timeout: float = 5.0
    _client: "AdminClient" | None = field(init=False, default=None, repr=False)
    _new_topic_cls: type | None = field(init=False, default=None, repr=False)
    _config_resource_cls: type | None = field(init=False, default=None, repr=False)
    _kafka_exception_cls: type | None = field(init=False, default=None, repr=False)
    _kafka_error_cls: type | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        try:  # pragma: no cover - optional dependency
            from confluent_kafka import KafkaException, KafkaError
            from confluent_kafka.admin import AdminClient, ConfigResource, NewTopic
        except Exception as exc:  # pragma: no cover - env dependent
            logging.warning(
                "confluent-kafka unavailable; DAG Manager GC cannot query broker metadata: %s",
                exc,
            )
            return

        config = {
            "bootstrap.servers": self.bootstrap_servers,
            "api.version.request": "true",
        }
        try:
            self._client = AdminClient(config)
        except Exception as exc:  # pragma: no cover - connection failure
            logging.warning(
                "Failed to initialise Kafka AdminClient for %s: %s",
                self.bootstrap_servers,
                exc,
            )
            return

        self._new_topic_cls = NewTopic
        self._config_resource_cls = ConfigResource
        self._kafka_exception_cls = KafkaException
        self._kafka_error_cls = KafkaError

    # ------------------------------------------------------------------
    def _ensure_client(self) -> None:
        if self._client is None:
            raise RuntimeError(
                "Kafka AdminClient not available; install confluent-kafka to enable broker metadata access"
            )

    def list_topics(self) -> Mapping[str, Mapping[str, object]]:
        if self._client is None:
            return {}

        metadata = self._client.list_topics(timeout=self.timeout)
        topics: dict[str, dict[str, object]] = {}
        for name, topic in metadata.topics.items():
            error = getattr(topic, "error", None)
            if error is not None and hasattr(error, "code"):
                if self._kafka_error_cls is not None and error.code() != self._kafka_error_cls.NO_ERROR:  # type: ignore[attr-defined]
                    continue
            partitions = getattr(topic, "partitions", {}) or {}
            replication = 0
            if partitions:
                try:
                    replication = max(len(p.replicas) for p in partitions.values())
                except Exception:  # pragma: no cover - defensive
                    replication = 0
            topics[name] = {
                "config": {},
                "num_partitions": len(partitions),
                "replication_factor": replication,
            }

        config_cls = self._config_resource_cls
        if topics and config_cls is not None:
            resources = []
            for name in topics:
                try:
                    resource = config_cls(config_cls.Type.TOPIC, name)
                except AttributeError:  # pragma: no cover - legacy API
                    resource = config_cls("topic", name)
                resources.append(resource)
            try:
                futures = self._client.describe_configs(resources)
            except Exception:  # pragma: no cover - broker compatibility
                futures = {}
            for resource, future in futures.items():
                name = getattr(resource, "name", None)
                if name not in topics:
                    continue
                try:
                    entries = future.result(timeout=self.timeout)
                except Exception:  # pragma: no cover - partial failure
                    continue
                config: dict[str, object] = {}
                for entry in entries.values():
                    value = getattr(entry, "value", None)
                    if value is not None:
                        config[entry.name] = value
                topics[name]["config"] = config
        return topics

    def create_topic(
        self,
        name: str,
        *,
        num_partitions: int,
        replication_factor: int,
        config: Mapping[str, object] | None = None,
    ) -> None:
        self._ensure_client()
        assert self._client is not None  # for type checkers
        if self._new_topic_cls is None:
            raise RuntimeError("Kafka NewTopic helper unavailable")
        topic = self._new_topic_cls(
            name,
            num_partitions=int(num_partitions),
            replication_factor=int(replication_factor),
            config={k: str(v) for k, v in (config or {}).items()},
        )
        futures = self._client.create_topics([topic], request_timeout=int(self.timeout))
        future = futures.get(name)
        if future is None:
            return
        try:
            future.result()
        except Exception as exc:  # pragma: no cover - depends on broker
            if (
                self._kafka_exception_cls is not None
                and isinstance(exc, self._kafka_exception_cls)
                and self._kafka_error_cls is not None
            ):
                err = exc.args[0]
                if getattr(err, "code", lambda: None)() == self._kafka_error_cls.TOPIC_ALREADY_EXISTS:
                    from .kafka_admin import TopicExistsError

                    raise TopicExistsError from exc
            raise

    def delete_topic(self, name: str) -> None:
        if self._client is None:
            return
        futures = self._client.delete_topics([name], operation_timeout=int(self.timeout))
        future = futures.get(name)
        if future is None:
            return
        with contextlib.suppress(Exception):  # pragma: no cover - optional dependency
            future.result()


async def _run(cfg: DagManagerConfig, *, enable_otel: bool = False) -> None:
    set_topic_namespace_enabled(cfg.enable_topic_namespace)
    driver = None
    repo = None
    admin_client = None
    queue = None
    kafka_admin = None

    if cfg.neo4j_dsn:
        from neo4j import GraphDatabase  # pragma: no cover - external dependency

        driver = GraphDatabase.driver(
            cfg.neo4j_dsn, auth=(cfg.neo4j_user, cfg.neo4j_password)
        )
        from .diff_service import Neo4jNodeRepository

        repo = Neo4jNodeRepository(driver)
    else:
        from .node_repository import MemoryNodeRepository

        repo = MemoryNodeRepository(cfg.memory_repo_path)

    if cfg.kafka_dsn:
        from .kafka_admin import KafkaAdmin
        from .diff_service import KafkaQueueManager

        admin_client = _KafkaAdminClient(cfg.kafka_dsn)
        # Manual reset of the breaker is expected after successful operations
        breaker = AsyncCircuitBreaker()
        kafka_admin = KafkaAdmin(admin_client, breaker=breaker)
        queue = KafkaQueueManager(kafka_admin)
    else:
        from .kafka_admin import InMemoryAdminClient, KafkaAdmin
        from .diff_service import KafkaQueueManager

        admin_client = InMemoryAdminClient()
        # Manual reset of the breaker is expected after successful operations
        breaker = AsyncCircuitBreaker()
        kafka_admin = KafkaAdmin(admin_client, breaker=breaker)
        queue = KafkaQueueManager(kafka_admin)

    metrics_provider: MetricsProvider = KafkaMetricsProvider(
        getattr(cfg, "kafka_metrics_url", None)
    )
    store: QueueStore = KafkaQueueStore(kafka_admin, repo)
    gc = GarbageCollector(store, metrics_provider)
    scheduler = GCScheduler(gc)

    bus = None
    try:
        if cfg.controlbus_dsn:
            bus = ControlBusProducer(
                brokers=[cfg.controlbus_dsn], topic=cfg.controlbus_queue_topic
            )
            await bus.start()

        grpc_server, _ = serve(
            driver,
            admin_client,
            _NullStream(),
            host=cfg.grpc_host,
            port=cfg.grpc_port,
            gc=gc,
            repo=repo,
            queue=queue,
            bus=bus,
        )
        await grpc_server.start()
        await scheduler.start()

        app = create_app(
            gc,
            driver=driver,
            bus=bus,
            repo=repo,
            enable_otel=enable_otel,
        )
        config = uvicorn.Config(
            app,
            host=cfg.http_host,
            port=cfg.http_port,
            loop="asyncio",
            log_level="info",
        )
        http_server = uvicorn.Server(config)

        await asyncio.gather(
            http_server.serve(), grpc_server.wait_for_termination()
        )
    finally:
        await scheduler.stop()
        if bus:
            await bus.stop()


def _extract_lang(argv: Sequence[str]) -> tuple[list[str], str | None]:
    rest: list[str] = []
    lang: str | None = None

    i = 0
    tokens = list(argv)
    while i < len(tokens):
        token = tokens[i]
        if token.startswith("--lang="):
            lang = token.split("=", 1)[1]
            i += 1
            continue
        if token in {"--lang", "-L"}:
            if i + 1 < len(tokens):
                lang = tokens[i + 1]
                i += 2
                continue
            i += 1
            continue
        rest.append(token)
        i += 1
    return rest, lang


def main(argv: list[str] | None = None) -> None:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    original_is_none = argv is None
    raw_argv, lang = _extract_lang(raw_argv)
    if lang is not None:
        set_language(lang)
    elif original_is_none:
        set_language(None)

    parser = argparse.ArgumentParser(
        prog="qmtl service dagmanager server",
        description=_("Run DAG Manager gRPC and HTTP servers"),
    )
    parser.add_argument("--config", help=_("Path to configuration file"))
    args = parser.parse_args(raw_argv)

    cfg_path = args.config or find_config_file()
    _log_config_source(cfg_path, cli_override=args.config)

    cfg = DagManagerConfig()
    telemetry_enabled: bool | None = None
    telemetry_endpoint: str | None = None
    if cfg_path:
        unified = load_config(cfg_path)
        if "dagmanager" not in unified.present_sections:
            logging.error(
                _(
                    "DAG Manager configuration file %s does not define the 'dagmanager' section."
                ),
                cfg_path,
            )
            raise SystemExit(2)
        cfg = unified.dagmanager
        telemetry_enabled = unified.telemetry.enable_fastapi_otel
        telemetry_endpoint = unified.telemetry.otel_exporter_endpoint

    setup_tracing(
        "dagmanager",
        exporter_endpoint=telemetry_endpoint,
        config_path=cfg_path,
    )

    asyncio.run(_run(cfg, enable_otel=bool(telemetry_enabled)))


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
