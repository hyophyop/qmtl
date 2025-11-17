from __future__ import annotations

"""Adapter protocols for optional infrastructure clients.

This module centralises lightweight Protocol definitions and factory helpers
for external clients that are optionally installed in deployments. Validation
routines and other call sites should interact with these protocols instead of
accessing concrete client attributes directly.
"""

from typing import Any, Protocol, Sequence


class KafkaAdminClient(Protocol):
    """Minimal Kafka admin surface required by validators."""

    def list_topics(self) -> object:
        ...


class BrokerReadinessProbe(Protocol):
    """Protocol for checking broker reachability."""

    async def ready(self) -> bool:
        ...


class AsyncpgConnection(Protocol):
    async def close(self) -> None:
        ...


class AioSqliteConnection(Protocol):
    async def close(self) -> None:
        ...


class RedisClient(Protocol):
    async def ping(self) -> Any:
        ...

    async def close(self) -> None:
        ...


class Neo4jSession(Protocol):
    def run(self, query: str) -> object:
        ...

    def close(self) -> None:
        ...

    def __enter__(self) -> "Neo4jSession":
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> object:
        ...


class Neo4jDriver(Protocol):
    def session(self) -> Neo4jSession:
        ...

    def close(self) -> None:
        ...


def create_kafka_admin_client(dsn: str) -> KafkaAdminClient:
    """Return a Kafka admin client adapter for ``dsn``."""

    from confluent_kafka.admin import AdminClient

    class _AdminClientAdapter:
        def __init__(self, client: AdminClient) -> None:
            self._client = client

        def list_topics(self) -> object:  # pragma: no cover - thin wrapper
            return self._client.list_topics()

    client = AdminClient({"bootstrap.servers": dsn})
    return _AdminClientAdapter(client)


def create_aiokafka_readiness_probe(
    brokers: Sequence[str], group: str
) -> BrokerReadinessProbe:
    """Return a readiness probe backed by ``aiokafka``."""

    from aiokafka import AIOKafkaConsumer

    class _AiokafkaProbe:
        def __init__(self, *, brokers: Sequence[str], group: str) -> None:
            self._brokers = brokers
            self._group = group

        async def ready(self) -> bool:
            consumer = AIOKafkaConsumer(
                bootstrap_servers=self._brokers,
                group_id=self._group,
                enable_auto_commit=False,
            )
            await consumer.start()
            await consumer.stop()
            return True

    return _AiokafkaProbe(brokers=brokers, group=group)


async def open_asyncpg_connection(dsn: str) -> AsyncpgConnection:
    """Open an ``asyncpg`` connection using ``dsn``."""

    import asyncpg

    return await asyncpg.connect(dsn)


async def open_aiosqlite_connection(path: str) -> AioSqliteConnection:
    """Open an ``aiosqlite`` connection using ``path``."""

    import aiosqlite

    return await aiosqlite.connect(path)


def create_redis_client(dsn: str) -> RedisClient:
    """Create an asyncio Redis client for ``dsn``."""

    import redis.asyncio as redis

    return redis.from_url(dsn)


def create_neo4j_driver(
    dsn: str, *, user: str | None = None, password: str | None = None
) -> Neo4jDriver:
    """Create a typed Neo4j driver adapter.

    Raises ``ModuleNotFoundError`` when the optional ``neo4j`` dependency is
    unavailable and propagates connection errors to the caller.
    """

    from neo4j import GraphDatabase

    class _Neo4jSessionAdapter:
        def __init__(self, session: Any) -> None:
            self._session = session

        def run(self, query: str) -> object:  # pragma: no cover - thin wrapper
            return self._session.run(query)

        def close(self) -> None:  # pragma: no cover - thin wrapper
            self._session.close()

        def __enter__(self) -> "Neo4jSession":  # pragma: no cover - thin wrapper
            self._session.__enter__()
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: Any,
        ) -> object:  # pragma: no cover - thin wrapper
            return self._session.__exit__(exc_type, exc, tb)

    class _Neo4jDriverAdapter:
        def __init__(self, driver: Any) -> None:
            self._driver = driver

        def session(self) -> Neo4jSession:  # pragma: no cover - thin wrapper
            return _Neo4jSessionAdapter(self._driver.session())

        def close(self) -> None:  # pragma: no cover - thin wrapper
            self._driver.close()

    driver = GraphDatabase.driver(dsn, auth=(user, password))
    return _Neo4jDriverAdapter(driver)


__all__ = [
    "Neo4jDriver",
    "Neo4jSession",
    "AsyncpgConnection",
    "AioSqliteConnection",
    "BrokerReadinessProbe",
    "KafkaAdminClient",
    "RedisClient",
    "create_aiokafka_readiness_probe",
    "create_kafka_admin_client",
    "create_redis_client",
    "create_neo4j_driver",
    "open_aiosqlite_connection",
    "open_asyncpg_connection",
]
