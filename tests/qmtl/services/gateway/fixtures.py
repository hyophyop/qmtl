from __future__ import annotations

import base64
import json
from http import HTTPStatus
from types import SimpleNamespace
from typing import Any, Awaitable, Callable

import httpx

from qmtl.foundation.common import crc32_of_list
from qmtl.services.gateway.database import (
    MemoryDatabase,
    PostgresDatabase,
    SQLiteDatabase,
)
from qmtl.services.gateway.models import StrategySubmit


class StubWorldClient:
    """Capture outbound WorldService binding sync requests."""

    def __init__(
        self,
        *,
        conflict_after: set[int] | None = None,
        fail_with: Exception | None = None,
    ) -> None:
        self.calls: list[tuple[str, dict[str, list[str]]]] = []
        self._call_count = 0
        self._conflict_after = conflict_after or set()
        self._fail_with = fail_with

    async def post_bindings(self, world_id: str, payload: dict, **_: object) -> None:
        self._call_count += 1
        self.calls.append((world_id, payload))
        if self._call_count in self._conflict_after:
            request = httpx.Request(
                "POST", f"http://world/worlds/{world_id}/bindings"
            )
            response = httpx.Response(HTTPStatus.CONFLICT, request=request)
            raise httpx.HTTPStatusError(
                "Conflict", request=request, response=response
            )
        if self._fail_with is not None:
            raise self._fail_with


class DummyManager:
    """StrategyManager stub capturing submissions and context flags."""

    def __init__(self) -> None:
        self.calls: list[StrategySubmit] = []
        self.skip_flags: list[bool] = []
        self.contexts: list[object] = []

    async def submit(
        self,
        payload: StrategySubmit,
        *,
        skip_downgrade_metric: bool = False,
        strategy_context=None,
    ) -> tuple[str, bool]:
        self.calls.append(payload)
        self.skip_flags.append(skip_downgrade_metric)
        self.contexts.append(strategy_context)
        return "strategy-abc", False


class DummyDagManager:
    """DagManager stub returning deterministic diff outcomes."""

    def __init__(self) -> None:
        self.tag_queries: list[tuple] = []
        self.diff_calls: list[tuple] = []
        self.raise_diff: bool = False
        self._queue_map = {"node123#0": "topic-A"}

    async def get_queues_by_tag(
        self, tags, interval, match_mode, world_id, execution_domain
    ):
        self.tag_queries.append(
            (tuple(tags), interval, match_mode, world_id, execution_domain)
        )
        return [
            {"queue": f"{world_id}:{tags[0]}" if world_id else f"global:{tags[0]}"}
        ]

    async def diff(
        self,
        strategy_id,
        dag_json,
        world_id=None,
        execution_domain=None,
        as_of=None,
        partition=None,
        dataset_fingerprint=None,
    ):
        self.diff_calls.append(
            (strategy_id, world_id, execution_domain, as_of, partition, dataset_fingerprint)
        )
        if self.raise_diff:
            raise TimeoutError("diff timeout")
        try:
            decoded = json.loads(base64.b64decode(dag_json).decode())
        except Exception:
            decoded = json.loads(dag_json)
        crc = crc32_of_list(n.get("node_id", "") for n in decoded.get("nodes", []))
        return SimpleNamespace(
            sentinel_id="diff-sentinel",
            queue_map=dict(self._queue_map),
            crc32=crc,
        )


class DummyDatabase:
    """Minimal database stub persisting world-strategy bindings in memory."""

    def __init__(self) -> None:
        self.bindings: list[tuple[str, str]] = []

    async def upsert_wsb(self, world_id: str, strategy_id: str) -> None:
        self.bindings.append((world_id, strategy_id))


async def build_memory_db(_: object | None = None):
    db = MemoryDatabase()

    async def fetch_bindings() -> set[tuple[str, str]]:
        return set(db.world_strategy_bindings)

    async def cleanup() -> None:
        return None

    return db, fetch_bindings, cleanup


async def build_sqlite_db(_: object | None = None):
    db = SQLiteDatabase("sqlite:///:memory:")
    await db.connect()

    async def fetch_bindings() -> set[tuple[str, str]]:
        assert db._conn
        async with db._conn.execute(
            "SELECT world_id, strategy_id FROM world_strategy_bindings"
        ) as cursor:
            rows = await cursor.fetchall()
        return {(world_id, strategy_id) for world_id, strategy_id in rows}

    async def cleanup() -> None:
        await db.close()

    return db, fetch_bindings, cleanup


async def build_postgres_db(monkeypatch) -> tuple[PostgresDatabase, Callable[[], Awaitable[set[tuple[str, str]]]], Callable[[], Awaitable[None]]]:
    class FakePool:
        def __init__(self) -> None:
            self.bindings: set[tuple[str, str]] = set()

        async def execute(self, query: str, *params) -> None:
            if params and "world_strategy_bindings" in query:
                self.bindings.add((params[0], params[1]))

        async def close(self) -> None:
            return None

    pool = FakePool()

    async def fake_create_pool(_dsn: str, *args, **kwargs):
        return pool

    monkeypatch.setattr(
        "qmtl.services.gateway.database.asyncpg.create_pool", fake_create_pool
    )

    db = PostgresDatabase("postgres://user:pass@localhost/db")
    await db.connect()

    async def fetch_bindings() -> set[tuple[str, str]]:
        return set(pool.bindings)

    async def cleanup() -> None:
        await db.close()

    return db, fetch_bindings, cleanup


DB_BUILDERS: dict[str, Callable[..., Awaitable[tuple[Any, Callable[[], Awaitable[set[tuple[str, str]]]], Callable[[], Awaitable[None]]]]]] = {
    "memory": build_memory_db,
    "sqlite": build_sqlite_db,
    "postgres": build_postgres_db,
}


__all__ = [
    "DB_BUILDERS",
    "DummyDagManager",
    "DummyDatabase",
    "DummyManager",
    "StubWorldClient",
    "build_memory_db",
    "build_postgres_db",
    "build_sqlite_db",
]
