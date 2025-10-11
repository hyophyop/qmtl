from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, fields
from typing import Any, Dict, Mapping, Sequence, get_args, get_origin, get_type_hints

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
            issues["worldservice"] = ValidationIssue(
                "ok", f"WorldService healthy at {config.worldservice_url}"
            )
        else:
            details: list[str] = []
            if result.status is not None:
                details.append(f"status={result.status}")
            if result.err:
                details.append(f"error={result.err}")
            if result.latency_ms is not None:
                details.append(f"latency_ms={result.latency_ms:.1f}")
            suffix = ", ".join(details) if details else "no additional detail"
            issues["worldservice"] = ValidationIssue(
                "error",
                f"WorldService probe failed ({result.code}): {suffix}",
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


def _type_description(annotation: Any) -> str:
    if annotation is Any:
        return "any"
    origin = get_origin(annotation)
    if origin is None:
        if annotation is type(None):  # pragma: no cover - explicit None type
            return "null"
        return getattr(annotation, "__name__", str(annotation))
    args = get_args(annotation)
    if origin in {list, Sequence}:
        inner = _type_description(args[0]) if args else "any"
        label = "list" if origin is list else "sequence"
        return f"{label}[{inner}]"
    if origin in {set, tuple}:
        inner = _type_description(args[0]) if args else "any"
        return f"{origin.__name__}[{inner}]"
    if origin in {dict, Mapping}:
        key_desc = _type_description(args[0]) if args else "any"
        value_desc = _type_description(args[1]) if len(args) > 1 else "any"
        return f"mapping[{key_desc}, {value_desc}]"
    if origin is tuple:
        inner_desc = ", ".join(_type_description(arg) for arg in args) if args else ""
        return f"tuple[{inner_desc}]"
    if origin is type(None):  # pragma: no cover - defensive
        return "null"
    return " | ".join(_type_description(arg) for arg in args)


def _value_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, list):
        inner = {type(item).__name__ for item in value}
        inner_desc = ",".join(sorted(inner)) or "unknown"
        return f"list[{inner_desc}]"
    if isinstance(value, tuple):
        return "tuple"
    if isinstance(value, set):
        inner = {type(item).__name__ for item in value}
        inner_desc = ",".join(sorted(inner)) or "unknown"
        return f"set[{inner_desc}]"
    if isinstance(value, dict):
        return "mapping"
    return type(value).__name__


def _type_matches(value: Any, annotation: Any) -> bool:
    if annotation is Any:
        return True
    origin = get_origin(annotation)
    if origin is None:
        if annotation is type(None):
            return value is None
        if isinstance(annotation, type):
            return isinstance(value, annotation)
        return True
    args = get_args(annotation)
    if origin in {list, Sequence}:
        if not isinstance(value, list):
            return False
        inner = args[0] if args else Any
        return all(_type_matches(item, inner) for item in value)
    if origin is tuple:
        if not isinstance(value, tuple):
            return False
        if not args:
            return True
        if len(args) == 2 and args[1] is Ellipsis:
            return all(_type_matches(item, args[0]) for item in value)
        if len(value) != len(args):
            return False
        return all(_type_matches(item, expected) for item, expected in zip(value, args))
    if origin is set:
        if not isinstance(value, set):
            return False
        inner = args[0] if args else Any
        return all(_type_matches(item, inner) for item in value)
    if origin in {dict, Mapping}:
        if not isinstance(value, dict):
            return False
        key_type = args[0] if args else Any
        value_type = args[1] if len(args) > 1 else Any
        return all(
            _type_matches(k, key_type) and _type_matches(v, value_type)
            for k, v in value.items()
        )
    if origin is Sequence:
        if isinstance(value, (str, bytes)):
            return False
        if not isinstance(value, Sequence):
            return False
        inner = args[0] if args else Any
        return all(_type_matches(item, inner) for item in value)
    return any(_type_matches(value, option) for option in args)


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
