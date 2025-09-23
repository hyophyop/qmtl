from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from qmtl.foundation.common import crc32_of_list
from qmtl.foundation.common.compute_context import DowngradeReason
from qmtl.services.gateway import metrics
from qmtl.services.gateway.database import MemoryDatabase, PostgresDatabase, SQLiteDatabase
from qmtl.services.gateway.models import StrategySubmit
from qmtl.services.gateway.strategy_submission import (
    StrategySubmissionConfig,
    StrategySubmissionHelper,
)
from qmtl.services.gateway.submission.context_service import StrategyComputeContext

from tests.gateway.helpers import build_strategy_payload


class DummyManager:
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
    def __init__(self) -> None:
        self.tag_queries: list[tuple] = []
        self.diff_calls: list[tuple] = []
        self.raise_diff: bool = False
        self.diff_result = SimpleNamespace(
            sentinel_id="diff-sentinel",
            queue_map={"node123#0": "topic-A"},
        )

    async def get_queues_by_tag(
        self, tags, interval, match_mode, world_id, execution_domain
    ):
        self.tag_queries.append((tuple(tags), interval, match_mode, world_id, execution_domain))
        return [{"queue": f"{world_id}:{tags[0]}" if world_id else f"global:{tags[0]}"}]

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
        self.diff_calls.append((strategy_id, world_id, execution_domain, as_of, partition, dataset_fingerprint))
        if self.raise_diff:
            raise TimeoutError("diff timeout")
        return self.diff_result


class DummyDatabase:
    def __init__(self) -> None:
        self.bindings: list[tuple[str, str]] = []

    async def upsert_wsb(self, world_id: str, strategy_id: str) -> None:
        self.bindings.append((world_id, strategy_id))


async def _build_memory_db(_monkeypatch):
    db = MemoryDatabase()

    async def fetch_bindings() -> set[tuple[str, str]]:
        return set(db.world_strategy_bindings)

    async def cleanup() -> None:
        return None

    return db, fetch_bindings, cleanup


async def _build_sqlite_db(_monkeypatch):
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


async def _build_postgres_db(monkeypatch):
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

    monkeypatch.setattr("qmtl.services.gateway.database.asyncpg.create_pool", fake_create_pool)

    db = PostgresDatabase("postgres://user:pass@localhost/db")
    await db.connect()

    async def fetch_bindings() -> set[tuple[str, str]]:
        return set(pool.bindings)

    async def cleanup() -> None:
        await db.close()

    return db, fetch_bindings, cleanup


@pytest.mark.asyncio
async def test_process_submission_uses_queries_and_diff_for_strategy():
    manager = DummyManager()
    dagmanager = DummyDagManager()
    database = DummyDatabase()
    helper = StrategySubmissionHelper(manager, dagmanager, database)
    bundle = build_strategy_payload()

    result = await helper.process(
        bundle.payload,
        StrategySubmissionConfig(
            submit=True,
            diff_timeout=0.1,
        ),
    )

    assert result.strategy_id == "strategy-abc"
    assert result.sentinel_id == "diff-sentinel"
    assert result.queue_map.keys() == {bundle.expected_node_id}
    queues = result.queue_map[bundle.expected_node_id]
    assert queues and queues[0]["queue"] == "world-1:alpha"
    assert database.bindings == [("world-1", "strategy-abc")]
    assert dagmanager.diff_calls, "diff should be invoked for sentinel lookup"
    strategy_id, world_id, domain, as_of, partition, dataset_fingerprint = dagmanager.diff_calls[0]
    assert manager.contexts and isinstance(manager.contexts[0], StrategyComputeContext)
    assert strategy_id == "strategy-abc"
    assert domain == "backtest"
    assert as_of == "2025-01-01T00:00:00Z"
    assert partition is None
    assert dataset_fingerprint is None
    assert dagmanager.tag_queries[0][-1] == "backtest"


@pytest.mark.asyncio
async def test_process_dry_run_prefers_diff_queue_map():
    dagmanager = DummyDagManager()
    helper = StrategySubmissionHelper(DummyManager(), dagmanager, DummyDatabase())
    bundle = build_strategy_payload()

    result = await helper.process(
        bundle.payload,
        StrategySubmissionConfig(
            submit=False,
            strategy_id="dryrun",
            diff_timeout=0.5,
            prefer_diff_queue_map=True,
            sentinel_default="",
            diff_strategy_id="dryrun",
            use_crc_sentinel_fallback=True,
        ),
    )

    assert result.strategy_id == "dryrun"
    assert result.queue_map == {"node123": [{"queue": "topic-A", "global": False}]}
    assert not dagmanager.tag_queries, "diff path should avoid tag query lookups"
    assert result.sentinel_id == "diff-sentinel"


@pytest.mark.asyncio
async def test_process_dryrun_missing_as_of_downgrades_to_backtest():
    metrics.reset_metrics()
    dagmanager = DummyDagManager()
    helper = StrategySubmissionHelper(DummyManager(), dagmanager, DummyDatabase())
    bundle = build_strategy_payload(
        execution_domain="dryrun",
        include_as_of=False,
    )

    result = await helper.process(
        bundle.payload,
        StrategySubmissionConfig(
            submit=False,
            strategy_id="dryrun",
            diff_timeout=0.3,
        ),
    )

    assert result.queue_map.keys() == {bundle.expected_node_id}
    assert dagmanager.diff_calls
    _, _, domain, as_of, _, _ = dagmanager.diff_calls[0]
    assert domain == "backtest"
    assert as_of is None
    assert dagmanager.tag_queries[0][-1] == "backtest"
    assert result.downgraded is True
    assert result.safe_mode is True
    assert result.downgrade_reason == DowngradeReason.MISSING_AS_OF
    metric_value = (
        metrics.strategy_compute_context_downgrade_total.labels(
            reason=DowngradeReason.MISSING_AS_OF.value
        )._value.get()
    )
    assert metric_value == 1


@pytest.mark.asyncio
async def test_process_backtest_missing_as_of_enters_safe_mode():
    metrics.reset_metrics()
    manager = DummyManager()
    dagmanager = DummyDagManager()
    helper = StrategySubmissionHelper(manager, dagmanager, DummyDatabase())
    bundle = build_strategy_payload(
        execution_domain="backtest",
        include_as_of=False,
    )

    result = await helper.process(
        bundle.payload,
        StrategySubmissionConfig(
            submit=True,
            diff_timeout=0.2,
        ),
    )

    assert result.queue_map.keys() == {bundle.expected_node_id}
    assert result.downgraded is True
    assert result.safe_mode is True
    assert result.downgrade_reason == DowngradeReason.MISSING_AS_OF
    assert dagmanager.diff_calls
    _, _, domain, as_of, _, _ = dagmanager.diff_calls[0]
    assert domain == "backtest"
    assert as_of is None
    assert manager.skip_flags == [True]
    metric_value = (
        metrics.strategy_compute_context_downgrade_total.labels(
            reason=DowngradeReason.MISSING_AS_OF.value
        )._value.get()
    )
    assert metric_value == 1


@pytest.mark.asyncio
async def test_process_dryrun_synonym_with_as_of_keeps_domain():
    metrics.reset_metrics()
    dagmanager = DummyDagManager()
    helper = StrategySubmissionHelper(DummyManager(), dagmanager, DummyDatabase())
    bundle = build_strategy_payload(execution_domain="paper")

    await helper.process(
        bundle.payload,
        StrategySubmissionConfig(
            submit=False,
            strategy_id="dryrun",
            diff_timeout=0.3,
        ),
    )

    assert dagmanager.diff_calls
    _, _, domain, as_of, _, _ = dagmanager.diff_calls[0]
    assert domain == "dryrun"
    assert as_of == "2025-01-01T00:00:00Z"
    assert dagmanager.tag_queries[0][-1] == "dryrun"
    metric_value = (
        metrics.strategy_compute_context_downgrade_total.labels(
            reason=DowngradeReason.MISSING_AS_OF.value
        )._value.get()
    )
    assert metric_value == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "config",
    [
        StrategySubmissionConfig(submit=True, diff_timeout=0.1),
        StrategySubmissionConfig(
            submit=False,
            strategy_id="dryrun",
            diff_timeout=0.5,
            prefer_diff_queue_map=True,
            sentinel_default="",
            diff_strategy_id="dryrun",
            use_crc_sentinel_fallback=True,
        ),
    ],
    ids=["submit", "dry-run"],
)
async def test_shared_validation_path(config: StrategySubmissionConfig) -> None:
    helper = StrategySubmissionHelper(DummyManager(), DummyDagManager(), DummyDatabase())
    bundle = build_strategy_payload(mismatch=True)

    with pytest.raises(HTTPException) as exc:
        await helper.process(bundle.payload, config)

    detail = exc.value.detail
    assert detail["code"] == "E_NODE_ID_MISMATCH"


@pytest.mark.asyncio
async def test_dry_run_diff_failure_falls_back_to_queries_and_crc() -> None:
    dagmanager = DummyDagManager()
    dagmanager.raise_diff = True
    helper = StrategySubmissionHelper(DummyManager(), dagmanager, DummyDatabase())
    bundle = build_strategy_payload()

    result = await helper.process(
        bundle.payload,
        StrategySubmissionConfig(
            submit=False,
            strategy_id="dryrun",
            diff_timeout=0.5,
            prefer_diff_queue_map=True,
            sentinel_default="",
            diff_strategy_id="dryrun",
            use_crc_sentinel_fallback=True,
        ),
    )

    assert result.queue_map.keys() == {bundle.expected_node_id}
    assert result.queue_map[bundle.expected_node_id][0]["queue"] == "world-1:alpha"
    expected_crc = crc32_of_list(
        n.get("node_id", "") for n in bundle.dag.get("nodes", [])
    )
    assert result.sentinel_id == f"dryrun:{expected_crc:08x}"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "db_builder",
    [_build_memory_db, _build_sqlite_db, _build_postgres_db],
    ids=["memory", "sqlite", "postgres"],
)
async def test_world_bindings_persist_for_all_databases(db_builder, monkeypatch) -> None:
    db, fetch_bindings, cleanup = await db_builder(monkeypatch)
    helper = StrategySubmissionHelper(DummyManager(), DummyDagManager(), db)
    bundle = build_strategy_payload()
    config = StrategySubmissionConfig(submit=True, diff_timeout=0.1)

    try:
        await helper.process(bundle.payload, config)
        await helper.process(bundle.payload, config)
        bindings = await fetch_bindings()
        assert bindings == {("world-1", "strategy-abc")}
    finally:
        await cleanup()
