# Database backends for Gateway

from __future__ import annotations

import json
import logging
from typing import Optional

import asyncpg
import aiosqlite

logger = logging.getLogger(__name__)

_INITIAL_STATUS = "queued"


class Database:
    async def insert_strategy(self, strategy_id: str, meta: Optional[dict]) -> None:
        raise NotImplementedError

    async def set_status(self, strategy_id: str, status: str) -> None:
        raise NotImplementedError

    async def get_status(self, strategy_id: str) -> Optional[str]:
        raise NotImplementedError

    async def append_event(self, strategy_id: str, event: str) -> None:
        raise NotImplementedError

    async def healthy(self) -> bool:
        raise NotImplementedError

    async def close(self) -> None:
        """Release any held resources."""
        # Default implementation for backends that do not need cleanup
        return None


class PostgresDatabase(Database):
    """PostgreSQL-backed implementation."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(self._dsn)
        await self._pool.execute(
            """
            CREATE TABLE IF NOT EXISTS strategies (
                id TEXT PRIMARY KEY,
                meta JSONB,
                status TEXT
            )
            """
        )
        await self._pool.execute(
            """
            CREATE TABLE IF NOT EXISTS strategy_events (
                id SERIAL PRIMARY KEY,
                strategy_id TEXT,
                event TEXT,
                ts TIMESTAMPTZ DEFAULT now()
            )
            """
        )
        await self._pool.execute(
            """
            CREATE TABLE IF NOT EXISTS event_log (
                id SERIAL PRIMARY KEY,
                strategy_id TEXT,
                event TEXT,
                ts TIMESTAMPTZ DEFAULT now()
            )
            """
        )

    async def insert_strategy(self, strategy_id: str, meta: Optional[dict]) -> None:
        assert self._pool
        await self._pool.execute(
            "INSERT INTO strategies(id, meta, status) VALUES($1, $2, $3)",
            strategy_id,
            json.dumps(meta) if meta is not None else None,
            _INITIAL_STATUS,
        )
        await self.append_event(strategy_id, f"INIT:{_INITIAL_STATUS}")

    async def set_status(self, strategy_id: str, status: str) -> None:
        assert self._pool
        await self._pool.execute(
            "UPDATE strategies SET status=$1 WHERE id=$2",
            status,
            strategy_id,
        )

    async def append_event(self, strategy_id: str, event: str) -> None:
        assert self._pool
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SET LOCAL synchronous_commit = 'on'")
                await conn.execute(
                    "INSERT INTO strategy_events(strategy_id, event) VALUES($1, $2)",
                    strategy_id,
                    event,
                )
                await conn.execute(
                    "INSERT INTO event_log(strategy_id, event) VALUES($1, $2)",
                    strategy_id,
                    event,
                )

    async def get_status(self, strategy_id: str) -> Optional[str]:
        assert self._pool
        row = await self._pool.fetchrow(
            "SELECT status FROM strategies WHERE id=$1",
            strategy_id,
        )
        return row["status"] if row else None

    async def healthy(self) -> bool:
        if self._pool is None:
            return False
        try:
            await self._pool.execute("SELECT 1")
            return True
        except Exception:
            return False

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()


class SQLiteDatabase(Database):
    """SQLite-backed implementation using :mod:`aiosqlite`."""

    def __init__(self, dsn: str) -> None:
        if dsn.startswith("sqlite:///"):
            self._path = dsn[len("sqlite:///") :]
        elif dsn.startswith("sqlite://"):
            self._path = dsn[len("sqlite://") :]
        else:
            self._path = dsn
        if not self._path:
            self._path = ":memory:"
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS strategies (
                id TEXT PRIMARY KEY,
                meta TEXT,
                status TEXT
            )
            """
        )
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS strategy_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT,
                event TEXT,
                ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS event_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT,
                event TEXT,
                ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await self._conn.commit()

    async def insert_strategy(self, strategy_id: str, meta: Optional[dict]) -> None:
        assert self._conn
        await self._conn.execute(
            "INSERT INTO strategies(id, meta, status) VALUES(?, ?, ?)",
            (strategy_id, json.dumps(meta) if meta is not None else None, _INITIAL_STATUS),
        )
        await self._conn.commit()
        await self.append_event(strategy_id, f"INIT:{_INITIAL_STATUS}")

    async def set_status(self, strategy_id: str, status: str) -> None:
        assert self._conn
        await self._conn.execute(
            "UPDATE strategies SET status=? WHERE id=?",
            (status, strategy_id),
        )
        await self._conn.commit()

    async def append_event(self, strategy_id: str, event: str) -> None:
        assert self._conn
        await self._conn.execute(
            "INSERT INTO strategy_events(strategy_id, event) VALUES(?, ?)",
            (strategy_id, event),
        )
        await self._conn.execute(
            "INSERT INTO event_log(strategy_id, event) VALUES(?, ?)",
            (strategy_id, event),
        )
        await self._conn.commit()

    async def get_status(self, strategy_id: str) -> Optional[str]:
        assert self._conn
        async with self._conn.execute(
            "SELECT status FROM strategies WHERE id=?",
            (strategy_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

    async def healthy(self) -> bool:
        if self._conn is None:
            return False
        try:
            await self._conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()


class MemoryDatabase(Database):
    """In-memory database stub used for testing or development."""

    def __init__(self) -> None:
        self.strategies: dict[str, dict] = {}
        self.events: list[tuple[str, str]] = []

    async def insert_strategy(self, strategy_id: str, meta: Optional[dict]) -> None:
        self.strategies[strategy_id] = {"meta": meta, "status": _INITIAL_STATUS}
        await self.append_event(strategy_id, f"INIT:{_INITIAL_STATUS}")

    async def set_status(self, strategy_id: str, status: str) -> None:
        if strategy_id in self.strategies:
            self.strategies[strategy_id]["status"] = status

    async def get_status(self, strategy_id: str) -> Optional[str]:
        data = self.strategies.get(strategy_id)
        return data["status"] if data else None

    async def append_event(self, strategy_id: str, event: str) -> None:
        self.events.append((strategy_id, event))

    async def healthy(self) -> bool:
        return True


__all__ = [
    "Database",
    "PostgresDatabase",
    "SQLiteDatabase",
    "MemoryDatabase",
]
