from __future__ import annotations

import asyncio
import contextlib
import importlib
from dataclasses import dataclass, fields
from typing import Any, Dict, Mapping, Sequence, TYPE_CHECKING, get_type_hints

import httpx  # test compatibility: referenced via monkeypatch in tests

from qmtl.foundation.adapters import (
    KafkaAdminClient,
    Neo4jDriver,
    create_aiokafka_readiness_probe,
    create_kafka_admin_client,
    create_neo4j_driver,
    create_redis_client,
    open_aiosqlite_connection,
    open_asyncpg_connection,
)
from qmtl.foundation.common.health import probe_http_async
from qmtl.foundation.config import (
    CONFIG_SECTION_NAMES,
    DeploymentProfile,
    UnifiedConfig,
)
from qmtl.foundation.config_types import (
    _type_description,
    _type_matches,
    _value_type_name,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from qmtl.services.dagmanager.config import DagManagerConfig
    from qmtl.services.gateway.config import GatewayConfig
    from qmtl.services.worldservice.config import WorldServiceServerConfig


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


async def _create_kafka_admin(dsn: str) -> KafkaAdminClient:
    return create_kafka_admin_client(dsn)


async def _check_controlbus(
    brokers: Sequence[str],
    topics: Sequence[str],
    group: str,
    *,
    offline: bool,
    required: bool = False,
) -> ValidationIssue:
    broker_list = ", ".join(brokers)
    if not brokers or not topics:
        severity = "error" if required else "warning"
        hint = (
            "ControlBus requires brokers/topics; configure controlbus_brokers and topics"
            if required
            else "ControlBus disabled; no brokers/topics configured"
        )
        return ValidationIssue(severity, hint)
    if offline:
        return ValidationIssue("warning", f"Offline mode: skipped ControlBus check for {broker_list}")
    try:
        probe = create_aiokafka_readiness_probe(brokers, group)
    except ModuleNotFoundError:
        return ValidationIssue("warning", "aiokafka not installed; skipping ControlBus validation")

    ready = await probe.ready()
    if ready:
        return ValidationIssue("ok", f"ControlBus brokers reachable ({broker_list})")
    return ValidationIssue("error", f"ControlBus brokers unreachable ({broker_list})")


async def _validate_gateway_redis(
    dsn: str | None, *, offline: bool, profile: DeploymentProfile
) -> ValidationIssue:
    if not dsn:
        if profile is DeploymentProfile.PROD:
            return ValidationIssue(
                "error",
                "Prod profile requires gateway.redis_dsn for persistent state",
            )
        return ValidationIssue(
            "warning", "Redis DSN not configured; falling back to in-memory store"
        )
    if offline:
        return ValidationIssue("warning", f"Offline mode: skipped Redis ping for {dsn}")

    client = None
    try:
        client = create_redis_client(dsn)
        await client.ping()
    except Exception as exc:
        return ValidationIssue("error", f"Redis connection failed: {exc}")
    finally:
        if client is not None:
            with contextlib.suppress(Exception):
                await client.close()

    return ValidationIssue("ok", f"Redis reachable at {dsn}")


async def _validate_gateway_database(
    config: "GatewayConfig", *, offline: bool, profile: DeploymentProfile
) -> ValidationIssue:
    backend = (config.database_backend or "").lower()
    if profile is DeploymentProfile.PROD and backend != "postgres":
        return ValidationIssue(
            "error",
            "Prod profile requires database_backend='postgres' with a DSN",
        )
    if backend == "postgres":
        if profile is DeploymentProfile.PROD and not config.database_dsn:
            return ValidationIssue(
                "error", "Prod profile requires gateway.database_dsn"
            )
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
        conn = await open_asyncpg_connection(dsn)
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
        conn = await open_aiosqlite_connection(path)
    except Exception as exc:
        return ValidationIssue("error", f"SQLite open failed for {path}: {exc}")
    finally:
        if conn is not None:
            with contextlib.suppress(Exception):
                await conn.close()

    return ValidationIssue("ok", f"SQLite ready at {path}")


async def _validate_gateway_worldservice(
    config: "GatewayConfig", *, offline: bool
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


def validate_worldservice_config(
    server: "WorldServiceServerConfig" | None,
    *,
    profile: DeploymentProfile = DeploymentProfile.DEV,
) -> Dict[str, ValidationIssue]:
    issues: Dict[str, ValidationIssue] = {}
    if server is None:
        issues["server"] = ValidationIssue(
            "ok", "WorldService inline server not configured"
        )
        return issues

    if profile is DeploymentProfile.PROD and not server.redis:
        issues["redis"] = ValidationIssue(
            "error",
            "Prod profile requires worldservice.server.redis for activation storage",
        )
    else:
        severity = "ok" if server.redis else "warning"
        hint = (
            f"Redis configured at {server.redis}"
            if server.redis
            else "Redis not configured; using in-memory activation store"
        )
        issues["redis"] = ValidationIssue(severity, hint)

    issues["database"] = ValidationIssue("ok", "WorldService DSN provided")
    return issues


def _validate_gateway_commitlog(
    config: "GatewayConfig", profile: DeploymentProfile
) -> ValidationIssue:
    if not config.commitlog_bootstrap:
        severity = "error" if profile is DeploymentProfile.PROD else "warning"
        hint = (
            "Prod profile requires commitlog_bootstrap for ingest durability"
            if profile is DeploymentProfile.PROD
            else "Commit-log writer disabled; expected for local dev"
        )
        return ValidationIssue(severity, hint)
    if not config.commitlog_topic:
        severity = "error" if profile is DeploymentProfile.PROD else "warning"
        return ValidationIssue(
            severity,
            "Commit-log topic missing; set gateway.commitlog_topic to enable",
        )
    return ValidationIssue("ok", f"Commit-log configured for {config.commitlog_topic}")


async def _validate_gateway_ownership(
    config: "GatewayConfig", *, offline: bool, profile: DeploymentProfile
) -> ValidationIssue:
    ownership = config.ownership
    if ownership.mode == "postgres":
        return ValidationIssue("ok", "Ownership uses Postgres advisory locks")

    if ownership.mode != "kafka":
        return ValidationIssue(
            "error", f"Unknown gateway.ownership.mode {ownership.mode}"
        )

    if not ownership.bootstrap:
        severity = "error" if profile is DeploymentProfile.PROD else "warning"
        return ValidationIssue(
            severity, "Kafka ownership requires gateway.ownership.bootstrap"
        )

    if not ownership.topic:
        severity = "error" if profile is DeploymentProfile.PROD else "warning"
        return ValidationIssue(
            severity, "Kafka ownership requires gateway.ownership.topic"
        )

    spec = importlib.util.find_spec("aiokafka")
    if spec is None:
        severity = "error" if profile is DeploymentProfile.PROD else "warning"
        return ValidationIssue(
            severity, "Install aiokafka to use gateway.ownership.mode=kafka"
        )

    if offline:
        return ValidationIssue("warning", "Offline mode: skipping Kafka ownership probe")

    aiokafka = importlib.import_module("aiokafka")
    consumer = aiokafka.AIOKafkaConsumer(
        ownership.topic,
        bootstrap_servers=ownership.bootstrap,
        group_id=ownership.group_id,
        enable_auto_commit=False,
    )

    try:
        await consumer.start()
        partitions = consumer.partitions_for_topic(ownership.topic) or set()
    except Exception as exc:  # pragma: no cover - defensive path
        severity = "error" if profile is DeploymentProfile.PROD else "warning"
        return ValidationIssue(
            severity, f"Kafka ownership connection failed: {exc!s}"
        )
    finally:
        with contextlib.suppress(Exception):
            await consumer.stop()

    if not partitions:
        severity = "error" if profile is DeploymentProfile.PROD else "warning"
        return ValidationIssue(
            severity, "Kafka ownership topic has no partitions configured"
        )

    return ValidationIssue(
        "ok", f"Kafka ownership enabled for {ownership.topic} ({len(partitions)} partitions)"
    )


async def _validate_gateway_controlbus(
    config: "GatewayConfig", *, offline: bool, profile: DeploymentProfile
) -> ValidationIssue:
    return await _check_controlbus(
        config.controlbus_brokers,
        config.controlbus_topics,
        config.controlbus_group,
        offline=offline,
        required=profile is DeploymentProfile.PROD,
    )


async def validate_gateway_config(
    config: "GatewayConfig",
    *,
    offline: bool = False,
    profile: DeploymentProfile = DeploymentProfile.DEV,
) -> Dict[str, ValidationIssue]:
    issues: Dict[str, ValidationIssue] = {}

    issues["redis"] = await _validate_gateway_redis(
        config.redis_dsn, offline=offline, profile=profile
    )
    issues["database"] = await _validate_gateway_database(
        config, offline=offline, profile=profile
    )
    issues["commitlog"] = _validate_gateway_commitlog(config, profile)
    issues["ownership"] = await _validate_gateway_ownership(
        config, offline=offline, profile=profile
    )
    issues["controlbus"] = await _validate_gateway_controlbus(
        config, offline=offline, profile=profile
    )
    issues["worldservice"] = await _validate_gateway_worldservice(config, offline=offline)

    return issues


async def validate_dagmanager_config(
    config: "DagManagerConfig",
    *,
    offline: bool = False,
    profile: DeploymentProfile = DeploymentProfile.DEV,
) -> Dict[str, ValidationIssue]:
    issues: Dict[str, ValidationIssue] = {}
    if profile is DeploymentProfile.PROD and not config.neo4j_dsn:
        issues["neo4j"] = ValidationIssue(
            "error", "Prod profile requires dagmanager.neo4j_dsn"
        )
    else:
        issues["neo4j"] = await _validate_dagmanager_neo4j(config, offline=offline)

    if profile is DeploymentProfile.PROD and not config.kafka_dsn:
        issues["kafka"] = ValidationIssue(
            "error", "Prod profile requires dagmanager.kafka_dsn"
        )
    else:
        issues["kafka"] = await _validate_dagmanager_kafka(config, offline=offline)

    issues["controlbus"] = await _validate_dagmanager_controlbus(
        config, offline=offline, profile=profile
    )
    return issues


async def _validate_dagmanager_neo4j(
    config: "DagManagerConfig", *, offline: bool
) -> ValidationIssue:
    if not config.neo4j_dsn:
        return ValidationIssue(
            "warning", "Neo4j disabled; using memory repository (dev-only fallback)"
        )
    if offline:
        return ValidationIssue(
            "warning", f"Offline mode: skipped Neo4j check for {config.neo4j_dsn}"
        )

    driver: Neo4jDriver | None = None
    try:
        driver = create_neo4j_driver(
            config.neo4j_dsn,
            user=config.neo4j_user,
            password=config.neo4j_password,
        )
    except ModuleNotFoundError:
        return ValidationIssue(
            "warning", "neo4j driver not installed; skipping validation"
        )
    except Exception as exc:
        return ValidationIssue("error", f"Neo4j connection failed: {exc}")

    loop = asyncio.get_running_loop()

    def _probe(active_driver: Neo4jDriver) -> None:
        with active_driver.session() as session:
            session.run("RETURN 1")

    try:
        await loop.run_in_executor(None, _probe, driver)
    except Exception as exc:
        return ValidationIssue("error", f"Neo4j connection failed: {exc}")
    finally:
        if driver is not None:
            with contextlib.suppress(Exception):
                driver.close()

    return ValidationIssue("ok", f"Neo4j reachable at {config.neo4j_dsn}")


async def _validate_dagmanager_kafka(
    config: "DagManagerConfig", *, offline: bool
) -> ValidationIssue:
    if not config.kafka_dsn:
        return ValidationIssue(
            "warning",
            "Kafka DSN not configured; using in-memory queue manager (dev-only fallback)",
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
        return admin.list_topics()

    try:
        metadata = await loop.run_in_executor(None, _fetch)
    except Exception as exc:
        return ValidationIssue("error", f"Kafka metadata fetch failed: {exc}")

    count = _count_topics(metadata)
    return ValidationIssue(
        "ok", f"Kafka reachable at {config.kafka_dsn} ({count} topics visible)"
    )


async def _validate_dagmanager_controlbus(
    config: "DagManagerConfig", *, offline: bool, profile: DeploymentProfile
) -> ValidationIssue:
    brokers = [config.controlbus_dsn] if config.controlbus_dsn else []
    topics = [config.controlbus_queue_topic] if config.controlbus_queue_topic else []
    return await _check_controlbus(
        brokers,
        topics,
        f"{config.controlbus_queue_topic}-validator",
        offline=offline,
        required=profile is DeploymentProfile.PROD,
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
    "validate_worldservice_config",
]
