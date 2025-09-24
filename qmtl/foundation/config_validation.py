from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Dict, Mapping, Sequence

import aiosqlite
import asyncpg
import httpx
import redis.asyncio as redis

from qmtl.services.dagmanager.config import DagManagerConfig
from qmtl.services.dagmanager.kafka_admin import KafkaAdmin
from qmtl.services.gateway.config import GatewayConfig
from qmtl.services.gateway.controlbus_consumer import ControlBusConsumer


@dataclass(slots=True)
class ValidationIssue:
    """Represents the outcome of a single validation check."""

    severity: str
    hint: str


def _normalise_sqlite_path(dsn: str | None) -> str:
    if not dsn:
        return ":memory:"
    if dsn.startswith("sqlite:///"):
        return dsn[len("sqlite:///") :]
    if dsn.startswith("sqlite://"):
        return dsn[len("sqlite://") :]
    return dsn or ":memory:"


def _count_topics(metadata: object) -> int:
    if isinstance(metadata, Mapping):
        return len(metadata)
    topics = getattr(metadata, "topics", None)
    if isinstance(topics, Mapping):
        return len(topics)
    if isinstance(topics, Sequence):
        return len(topics)
    if topics is None:
        return 0
    try:
        return len(list(topics))
    except Exception:
        return 0


async def _create_kafka_admin(dsn: str) -> KafkaAdmin:
    from confluent_kafka.admin import AdminClient  # type: ignore[import]

    client = AdminClient({"bootstrap.servers": dsn})
    return KafkaAdmin(client)


async def _check_controlbus(
    brokers: Sequence[str], topics: Sequence[str], group: str, *, offline: bool
) -> ValidationIssue:
    broker_list = ", ".join(brokers)
    if not brokers or not topics:
        return ValidationIssue("ok", "ControlBus disabled; no brokers/topics configured")
    if offline:
        return ValidationIssue("warning", f"Offline mode: skipped ControlBus check for {broker_list}")
    try:
        import aiokafka  # type: ignore[import]  # noqa: F401
    except ModuleNotFoundError:
        return ValidationIssue("warning", "aiokafka not installed; skipping ControlBus validation")

    consumer = ControlBusConsumer(brokers=list(brokers), topics=list(topics), group=group)
    ready = await consumer._broker_ready()
    if ready:
        return ValidationIssue("ok", f"ControlBus brokers reachable ({broker_list})")
    return ValidationIssue("error", f"ControlBus brokers unreachable ({broker_list})")


async def validate_gateway_config(
    config: GatewayConfig, *, offline: bool = False
) -> Dict[str, ValidationIssue]:
    issues: Dict[str, ValidationIssue] = {}

    # Redis connectivity
    if not config.redis_dsn:
        issues["redis"] = ValidationIssue(
            "warning", "Redis DSN not configured; falling back to in-memory store"
        )
    elif offline:
        issues["redis"] = ValidationIssue(
            "warning", f"Offline mode: skipped Redis ping for {config.redis_dsn}"
        )
    else:
        client = None
        try:
            client = redis.from_url(config.redis_dsn)
            await client.ping()
        except Exception as exc:
            issues["redis"] = ValidationIssue("error", f"Redis connection failed: {exc}")
        else:
            issues["redis"] = ValidationIssue("ok", f"Redis reachable at {config.redis_dsn}")
        finally:
            if client is not None:
                with contextlib.suppress(Exception):
                    await client.close()

    # Database backend
    backend = (config.database_backend or "").lower()
    if backend == "postgres":
        dsn = config.database_dsn or "postgresql://localhost/qmtl"
        if offline:
            issues["database"] = ValidationIssue(
                "warning", f"Offline mode: skipped Postgres check for {dsn}"
            )
        else:
            conn = None
            try:
                conn = await asyncpg.connect(dsn)
            except Exception as exc:
                issues["database"] = ValidationIssue(
                    "error", f"Postgres connection failed: {exc}"
                )
            else:
                issues["database"] = ValidationIssue(
                    "ok", f"Postgres reachable at {dsn}"
                )
            finally:
                if conn is not None:
                    with contextlib.suppress(Exception):
                        await conn.close()
    elif backend == "sqlite":
        path = _normalise_sqlite_path(config.database_dsn)
        conn = None
        try:
            conn = await aiosqlite.connect(path)
        except Exception as exc:
            issues["database"] = ValidationIssue(
                "error", f"SQLite open failed for {path}: {exc}"
            )
        else:
            issues["database"] = ValidationIssue("ok", f"SQLite ready at {path}")
        finally:
            if conn is not None:
                with contextlib.suppress(Exception):
                    await conn.close()
    elif backend == "memory":
        issues["database"] = ValidationIssue(
            "warning", "In-memory database configured; data will not persist"
        )
    else:
        issues["database"] = ValidationIssue(
            "error", f"Unsupported database backend '{config.database_backend}'"
        )

    # ControlBus consumer
    issues["controlbus"] = await _check_controlbus(
        config.controlbus_brokers,
        config.controlbus_topics,
        config.controlbus_group,
        offline=offline,
    )

    # WorldService proxy
    if not config.enable_worldservice_proxy or not config.worldservice_url:
        issues["worldservice"] = ValidationIssue(
            "ok", "WorldService proxy disabled"
        )
    elif offline:
        issues["worldservice"] = ValidationIssue(
            "warning",
            f"Offline mode: skipped WorldService health check for {config.worldservice_url}",
        )
    else:
        health_url = config.worldservice_url.rstrip("/") + "/health"
        timeout = max(config.worldservice_timeout, 0.1)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(health_url, timeout=timeout)
        except Exception as exc:
            issues["worldservice"] = ValidationIssue(
                "error", f"WorldService request failed: {exc}"
            )
        else:
            if resp.status_code == 200:
                issues["worldservice"] = ValidationIssue(
                    "ok", f"WorldService healthy at {config.worldservice_url}"
                )
            else:
                issues["worldservice"] = ValidationIssue(
                    "error",
                    f"WorldService health returned HTTP {resp.status_code}",
                )

    return issues


async def validate_dagmanager_config(
    config: DagManagerConfig, *, offline: bool = False
) -> Dict[str, ValidationIssue]:
    issues: Dict[str, ValidationIssue] = {}

    # Neo4j repository
    if not config.neo4j_dsn:
        issues["neo4j"] = ValidationIssue(
            "ok", "Neo4j disabled; using memory repository"
        )
    elif offline:
        issues["neo4j"] = ValidationIssue(
            "warning", f"Offline mode: skipped Neo4j check for {config.neo4j_dsn}"
        )
    else:
        try:
            from neo4j import GraphDatabase  # type: ignore[import]
        except ModuleNotFoundError:
            issues["neo4j"] = ValidationIssue(
                "warning", "neo4j driver not installed; skipping validation"
            )
        else:
            loop = asyncio.get_running_loop()

            def _probe() -> None:
                driver = GraphDatabase.driver(
                    config.neo4j_dsn, auth=(config.neo4j_user, config.neo4j_password)
                )
                try:
                    with driver.session() as session:
                        session.run("RETURN 1")
                finally:
                    driver.close()

            try:
                await loop.run_in_executor(None, _probe)
            except Exception as exc:
                issues["neo4j"] = ValidationIssue(
                    "error", f"Neo4j connection failed: {exc}"
                )
            else:
                issues["neo4j"] = ValidationIssue(
                    "ok", f"Neo4j reachable at {config.neo4j_dsn}"
                )

    # Kafka queue manager
    if not config.kafka_dsn:
        issues["kafka"] = ValidationIssue(
            "ok", "Kafka DSN not configured; using in-memory queue manager"
        )
    elif offline:
        issues["kafka"] = ValidationIssue(
            "warning", f"Offline mode: skipped Kafka admin check for {config.kafka_dsn}"
        )
    else:
        try:
            admin = await _create_kafka_admin(config.kafka_dsn)
        except ModuleNotFoundError:
            issues["kafka"] = ValidationIssue(
                "warning", "confluent-kafka not installed; skipping Kafka validation"
            )
        except Exception as exc:
            issues["kafka"] = ValidationIssue(
                "error", f"Failed to initialise Kafka admin client: {exc}"
            )
        else:
            loop = asyncio.get_running_loop()

            def _fetch() -> object:
                return admin.client.list_topics()

            try:
                metadata = await loop.run_in_executor(None, _fetch)
            except Exception as exc:
                issues["kafka"] = ValidationIssue(
                    "error", f"Kafka metadata fetch failed: {exc}"
                )
            else:
                count = _count_topics(metadata)
                issues["kafka"] = ValidationIssue(
                    "ok",
                    f"Kafka reachable at {config.kafka_dsn} ({count} topics visible)",
                )

    # ControlBus producer
    brokers = [config.controlbus_dsn] if config.controlbus_dsn else []
    topics = [config.controlbus_queue_topic] if config.controlbus_queue_topic else []
    issues["controlbus"] = await _check_controlbus(
        brokers, topics, f"{config.controlbus_queue_topic}-validator", offline=offline
    )

    return issues


__all__ = [
    "ValidationIssue",
    "validate_gateway_config",
    "validate_dagmanager_config",
]
