import pytest
from typing import Any, cast

from qmtl.services.gateway.database import PostgresDatabase
from qmtl.services.gateway.ownership import OwnershipManager


class FakeConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def fetchval(self, query: str, key: int) -> bool:
        self.calls.append((query, key))
        return True


class FakePool:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn

    def acquire(self):
        conn = self.conn

        class _Ctx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, exc_type, exc, tb):
                return None

        return _Ctx()


class FakeKafkaOwner:
    def __init__(self, result: bool) -> None:
        self.result = result
        self.acquire_calls: list[int] = []
        self.release_calls: list[int] = []

    async def acquire(self, key: int) -> bool:
        self.acquire_calls.append(key)
        return self.result

    async def release(self, key: int) -> None:
        self.release_calls.append(key)


@pytest.mark.asyncio
async def test_kafka_preferred_over_db() -> None:
    conn = FakeConn()
    db = PostgresDatabase("dsn")
    db._pool = cast(Any, FakePool(conn))
    kafka = FakeKafkaOwner(result=True)
    manager = OwnershipManager(db, kafka)

    assert await manager.acquire(10)
    assert kafka.acquire_calls == [10]
    assert conn.calls == []


@pytest.mark.asyncio
async def test_fallback_to_db_when_kafka_unavailable() -> None:
    conn = FakeConn()
    db = PostgresDatabase("dsn")
    db._pool = cast(Any, FakePool(conn))
    kafka = FakeKafkaOwner(result=False)
    manager = OwnershipManager(db, kafka)

    assert await manager.acquire(20)
    assert conn.calls == [("SELECT pg_try_advisory_lock($1)", 20)]


@pytest.mark.asyncio
async def test_release_unlocks_db_after_kafka_fallback() -> None:
    conn = FakeConn()
    db = PostgresDatabase("dsn")
    db._pool = cast(Any, FakePool(conn))
    kafka = FakeKafkaOwner(result=False)
    manager = OwnershipManager(db, kafka)

    assert await manager.acquire(25)
    await manager.release(25)

    assert kafka.release_calls == [25]
    assert conn.calls == [
        ("SELECT pg_try_advisory_lock($1)", 25),
        ("SELECT pg_advisory_unlock($1)", 25),
    ]


@pytest.mark.asyncio
async def test_release_uses_db_when_no_kafka_owner() -> None:
    conn = FakeConn()
    db = PostgresDatabase("dsn")
    db._pool = cast(Any, FakePool(conn))
    manager = OwnershipManager(db)

    await manager.release(30)
    assert conn.calls == [("SELECT pg_advisory_unlock($1)", 30)]
