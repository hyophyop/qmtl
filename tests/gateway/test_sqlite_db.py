import asyncio
import json
import pytest

from qmtl.gateway.database import SQLiteDatabase


@pytest.mark.asyncio
async def test_sqlite_crud(tmp_path):
    db_path = tmp_path / "test.db"
    db = SQLiteDatabase(f"sqlite:///{db_path}")
    await db.connect()
    await db.insert_strategy("s1", {"u": "a"})
    assert await db.get_status("s1") == "queued"

    await db.set_status("s1", "processing")
    assert await db.get_status("s1") == "processing"

    await db.append_event("s1", "PROCESS")
    assert await db.healthy() is True

    # Verify event persisted
    async with db._conn.execute(
        "SELECT COUNT(*) FROM strategy_events WHERE strategy_id=?",
        ("s1",),
    ) as cur:
        row = await cur.fetchone()
        assert row[0] >= 1
