from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, fields
from typing import Any, Dict, Mapping, Sequence, get_type_hints

import aiosqlite
import asyncpg
import redis.asyncio as redis
import httpx  # test compatibility: referenced via monkeypatch in tests

from qmtl.foundation.common.health import probe_http_async
from qmtl.foundation.config import CONFIG_SECTION_NAMES, UnifiedConfig
from qmtl.services.dagmanager.config import DagManagerConfig
from qmtl.services.dagmanager.kafka_admin import KafkaAdmin
from qmtl.services.gateway.config import GatewayConfig
from qmtl.services.gateway.controlbus_consumer import ControlBusConsumer
from qmtl.foundation.config_types import (
    _type_description,
    _type_matches,
    _value_type_name,
)


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
    topics = metadata if isinstance(metadata, Mapping) else getattr(metadata, "topics", None)
    if topics is None:
        return 0
    if isinstance(topics, Mapping):
        return len(topics)
    if isinstance(topics, Sequence):
        return len(topics)
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


async def _validate_gateway_redis(dsn: str | None, *, offline: bool) -> ValidationIssue:
    if not dsn:
        return ValidationIssue(
            "warning", "Redis DSN not configured; falling back to in-memory store"
        )
    if offline:
        return ValidationIssue("warning", f"Offline mode: skipped Redis ping for {dsn}")

    client = None
    try:
        client = redis.from_url(dsn)
        await client.ping()
    except Exception as exc:
        return ValidationIssue("error", f"Redis connection failed: {exc}")
    finally:
        if client is not None:
            with contextlib.suppress(Exception):
                await client.close()

    return ValidationIssue("ok", f"Redis reachable at {dsn}")


async def _validate_gateway_database(
    config: GatewayConfig, *, offline: bool
) -> ValidationIssue:
    backend = (config.database_backend or "").lower()
    if backend == "postgres":
        return await _validate_gateway_postgres(config.database_dsn, offline=offline)
    if backend == "sqlite":
        return await _validate_gateway_sqlite(config.database_dsn)
    if backend == "memory":
        return ValidationIssue(
            "warning", "In-memory database configured; data will not persist"
        )
    return ValidationIssue(
        "error", f"Unsupported database backend '{config.database_backend}'"
    )


async def _validate_gateway_postgres(
    dsn: str | None, *, offline: bool
) -> ValidationIssue:
    dsn = dsn or "postgresql://localhost/qmtl"
    if offline:
        return ValidationIssue("warning", f"Offline mode: skipped Postgres check for {dsn}")

    conn = None
    try:
        conn = await asyncpg.connect(dsn)
    except Exception as exc:
        return ValidationIssue("error", f"Postgres connection failed: {exc}")
    finally:
        if conn is not None:
            with contextlib.suppress(Exception):
                await conn.close()

    return ValidationIssue("ok", f"Postgres reachable at {dsn}")


async def _validate_gateway_sqlite(dsn: str | None) -> ValidationIssue:
    path = _normalise_sqlite_path(dsn)
    conn = None
    try:
        conn = await aiosqlite.connect(path)
    except Exception as exc:
        return ValidationIssue("error", f"SQLite open failed for {path}: {exc}")
    finally:
        if conn is not None:
            with contextlib.suppress(Exception):
                await conn.close()

    return ValidationIssue("ok", f"SQLite ready at {path}")


async def _validate_gateway_worldservice(
    config: GatewayConfig, *, offline: bool
) -> ValidationIssue:
    if not config.enable_worldservice_proxy or not config.worldservice_url:
        return ValidationIssue("ok", "WorldService proxy disabled")
    if offline:
        return ValidationIssue(
            "warning",
            f"Offline mode: skipped WorldService health check for {config.worldservice_url}",
        )

    async def _http_request(method: str, url: str, **kwargs):
        # Use GET for compatibility with tests that stub AsyncClient.get
        timeout = kwargs.get("timeout")
        async with httpx.AsyncClient() as client:
            if method.upper() == "GET":
                return await client.get(url, timeout=timeout)
            return await client.request(method, url, **kwargs)

    health_url = config.worldservice_url.rstrip("/") + "/health"
    timeout = max(config.worldservice_timeout, 0.1)
    result = await probe_http_async(
        health_url,
        service="worldservice",
        endpoint="/health",
        timeout=timeout,
        request=_http_request,
    )
    if result.ok:
        return ValidationIssue("ok", f"WorldService healthy at {config.worldservice_url}")

    suffix = _format_worldservice_probe(result)
    return ValidationIssue(
        "error", f"WorldService probe failed ({result.code}): {suffix}"
    )


def _format_worldservice_probe(result: object) -> str:
    details: list[str] = []
    status = getattr(result, "status", None)
    if status is not None:
        details.append(f"status={status}")
    err = getattr(result, "err", None)
    if err:
        details.append(f"error={err}")
    latency = getattr(result, "latency_ms", None)
    if latency is not None:
        details.append(f"latency_ms={latency:.1f}")
    return ", ".join(details) if details else "no additional detail"


async def validate_gateway_config(
    config: GatewayConfig, *, offline: bool = False
) -> Dict[str, ValidationIssue]:
    issues: Dict[str, ValidationIssue] = {}

    issues["redis"] = await _validate_gateway_redis(config.redis_dsn, offline=offline)
    issues["database"] = await _validate_gateway_database(config, offline=offline)
    issues["controlbus"] = await _check_controlbus(
        config.controlbus_brokers,
        config.controlbus_topics,
        config.controlbus_group,
        offline=offline,
    )
    issues["worldservice"] = await _validate_gateway_worldservice(config, offline=offline)

    return issues


async def validate_dagmanager_config(
    config: DagManagerConfig, *, offline: bool = False
) -> Dict[str, ValidationIssue]:
    return {
        "neo4j": await _validate_dagmanager_neo4j(config, offline=offline),
        "kafka": await _validate_dagmanager_kafka(config, offline=offline),
        "controlbus": await _validate_dagmanager_controlbus(config, offline=offline),
    }


async def _validate_dagmanager_neo4j(
    config: DagManagerConfig, *, offline: bool
) -> ValidationIssue:
    if not config.neo4j_dsn:
        return ValidationIssue("ok", "Neo4j disabled; using memory repository")
    if offline:
        return ValidationIssue(
            "warning", f"Offline mode: skipped Neo4j check for {config.neo4j_dsn}"
        )

    try:
        from neo4j import GraphDatabase  # type: ignore[import]
    except ModuleNotFoundError:
        return ValidationIssue(
            "warning", "neo4j driver not installed; skipping validation"
        )

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
        return ValidationIssue("error", f"Neo4j connection failed: {exc}")
    return ValidationIssue("ok", f"Neo4j reachable at {config.neo4j_dsn}")


async def _validate_dagmanager_kafka(
    config: DagManagerConfig, *, offline: bool
) -> ValidationIssue:
    if not config.kafka_dsn:
        return ValidationIssue(
            "ok", "Kafka DSN not configured; using in-memory queue manager"
        )
    if offline:
        return ValidationIssue(
            "warning", f"Offline mode: skipped Kafka admin check for {config.kafka_dsn}"
        )

    try:
        admin = await _create_kafka_admin(config.kafka_dsn)
    except ModuleNotFoundError:
        return ValidationIssue(
            "warning", "confluent-kafka not installed; skipping Kafka validation"
        )
    except Exception as exc:
        return ValidationIssue(
            "error", f"Failed to initialise Kafka admin client: {exc}"
        )

    loop = asyncio.get_running_loop()

    def _fetch() -> object:
        return admin.client.list_topics()

    try:
        metadata = await loop.run_in_executor(None, _fetch)
    except Exception as exc:
        return ValidationIssue("error", f"Kafka metadata fetch failed: {exc}")

    count = _count_topics(metadata)
    return ValidationIssue(
        "ok", f"Kafka reachable at {config.kafka_dsn} ({count} topics visible)"
    )


async def _validate_dagmanager_controlbus(
    config: DagManagerConfig, *, offline: bool
) -> ValidationIssue:
    brokers = [config.controlbus_dsn] if config.controlbus_dsn else []
    topics = [config.controlbus_queue_topic] if config.controlbus_queue_topic else []
    return await _check_controlbus(
        brokers, topics, f"{config.controlbus_queue_topic}-validator", offline=offline
    )


def validate_config_structure(unified: UnifiedConfig) -> Dict[str, ValidationIssue]:
    """Return per-section type validation results for ``UnifiedConfig``."""

    results: Dict[str, ValidationIssue] = {}
    for section in CONFIG_SECTION_NAMES:
        obj = getattr(unified, section, None)
        if obj is None:
            results[section] = ValidationIssue(
                "error", "Section missing from UnifiedConfig"
            )
            continue

        hints = get_type_hints(type(obj))
        errors: list[str] = []
        for field in fields(obj):
            expected = hints.get(field.name, Any)
            value = getattr(obj, field.name)
            if not _type_matches(value, expected):
                errors.append(
                    f"{field.name}: expected {_type_description(expected)}, got {_value_type_name(value)}"
                )

        if errors:
            results[section] = ValidationIssue("error", "; ".join(errors))
        else:
            results[section] = ValidationIssue(
                "ok", "All keys present with expected types"
            )

    return results


__all__ = [
    "ValidationIssue",
    "validate_gateway_config",
    "validate_dagmanager_config",
    "validate_config_structure",
]
