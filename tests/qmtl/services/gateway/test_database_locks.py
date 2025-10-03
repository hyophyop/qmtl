import pytest

from qmtl.services.gateway.database import pg_try_advisory_lock, pg_advisory_unlock


class FakeConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def fetchval(self, query: str, key: int) -> bool:
        self.calls.append((query, key))
        return True


@pytest.mark.asyncio
async def test_pg_try_advisory_lock_executes_correct_query() -> None:
    conn = FakeConn()
    assert await pg_try_advisory_lock(conn, 1)
    assert conn.calls == [("SELECT pg_try_advisory_lock($1)", 1)]


@pytest.mark.asyncio
async def test_pg_advisory_unlock_executes_correct_query() -> None:
    conn = FakeConn()
    assert await pg_advisory_unlock(conn, 2)
    assert conn.calls == [("SELECT pg_advisory_unlock($1)", 2)]
