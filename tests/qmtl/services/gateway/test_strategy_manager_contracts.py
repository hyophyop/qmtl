import base64
import json
from dataclasses import dataclass, field
from typing import Awaitable

import pytest
import redis.asyncio as redis
from typing import Any, cast
from fastapi import HTTPException

from qmtl.services.gateway import metrics
from qmtl.services.gateway.database import MemoryDatabase, PostgresDatabase
from qmtl.services.gateway.degradation import DegradationLevel
from qmtl.services.gateway.fsm import StrategyFSM
from qmtl.services.gateway.models import StrategySubmit
from qmtl.services.gateway.redis_client import InMemoryRedis
from qmtl.services.gateway.strategy_manager import StrategyManager


def _encode_dag(nodes: list[dict[str, Any]]) -> str:
    return base64.b64encode(json.dumps({"nodes": nodes}).encode()).decode()


def _make_payload(meta: dict[str, Any] | None = None) -> StrategySubmit:
    dag_json = _encode_dag([{"node_id": "n1", "node_type": "Base"}])
    return StrategySubmit(dag_json=dag_json, meta=meta, node_ids_crc32=0)


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    metrics.reset_metrics()


def _build_manager(
    *,
    commit_log_writer=None,
    degrade=None,
) -> StrategyManager:
    redis_client = cast(redis.Redis, InMemoryRedis())
    database = cast(PostgresDatabase, MemoryDatabase())
    fsm = StrategyFSM(redis=redis_client, database=database)
    return StrategyManager(
        redis=redis_client,
        database=database,
        fsm=fsm,
        commit_log_writer=commit_log_writer,
        degrade=degrade,
    )


class RecordingWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def publish_submission(self, strategy_id: str, record: dict) -> None:
        self.calls.append((strategy_id, record))


class FailingWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def publish_submission(self, strategy_id: str, record: dict) -> None:
        self.calls.append((strategy_id, record))
        raise RuntimeError("commit log offline")


@dataclass
class DegradationStub:
    level: DegradationLevel = DegradationLevel.NORMAL
    dag_ok: bool = True
    local_queue: list[str] = field(default_factory=list)


@pytest.mark.asyncio
async def test_submit_enriches_dag_with_version_sentinel() -> None:
    writer = RecordingWriter()
    manager = _build_manager(commit_log_writer=writer)
    payload = _make_payload(meta={"version": " 1.2.3 "})

    strategy_id, existed = await manager.submit(payload)

    assert not existed
    assert writer.calls, "commit log writer should receive the submission"
    _, record = writer.calls[0]
    sentinel = record["dag"]["nodes"][-1]
    assert sentinel["node_type"] == "VersionSentinel"
    assert sentinel["version"] == "1.2.3"

    stored = await cast(Awaitable[Any], manager.redis.hget(f"strategy:{strategy_id}", "dag"))
    dag_payload = json.loads(base64.b64decode(stored).decode())
    sentinel_copy = dag_payload["nodes"][-1]
    assert sentinel_copy["node_type"] == "VersionSentinel"
    assert sentinel_copy["version"] == "1.2.3"

    queued = await cast(Awaitable[Any], manager.redis.lpop("strategy_queue"))
    assert queued == strategy_id


@pytest.mark.asyncio
async def test_submit_deduplicates_existing_hash() -> None:
    writer = RecordingWriter()
    manager = _build_manager(commit_log_writer=writer)
    payload = _make_payload()

    first_id, first_existed = await manager.submit(payload)
    second_id, second_existed = await manager.submit(payload)

    assert not first_existed
    assert second_existed
    assert second_id == first_id
    assert len(writer.calls) == 1, "dedupe should skip additional commit log writes"

    first_queue_item = await cast(Awaitable[Any], manager.redis.lpop("strategy_queue"))
    second_queue_item = await cast(Awaitable[Any], manager.redis.lpop("strategy_queue"))
    assert first_queue_item == first_id
    assert second_queue_item is None


@pytest.mark.asyncio
async def test_submit_rolls_back_on_commit_log_failure() -> None:
    writer = FailingWriter()
    manager = _build_manager(commit_log_writer=writer)
    payload = _make_payload()

    with pytest.raises(HTTPException):
        await manager.submit(payload)

    assert writer.calls, "failing writer should still receive the attempt"
    strategy_id, record = writer.calls[0]
    dag_hash = record["dag_hash"]

    dag_entry = await cast(Awaitable[Any], manager.redis.hget(f"strategy:{strategy_id}", "dag"))
    assert dag_entry is None, "failed submissions must be rolled back"
    stored_hash = await manager.redis.get(f"dag_hash:{dag_hash}")
    assert stored_hash is None
    assert int(metrics.lost_requests_total._value.get()) == 1


@pytest.mark.asyncio
async def test_submit_respects_degradation_queueing() -> None:
    degrade = DegradationStub(level=DegradationLevel.PARTIAL, dag_ok=False)
    manager = _build_manager(degrade=degrade)
    payload = _make_payload()

    strategy_id, existed = await manager.submit(payload)

    assert not existed
    assert degrade.local_queue == [strategy_id], "strategy should queue locally during degradation"
    queued = await cast(Awaitable[Any], manager.redis.lpop("strategy_queue"))
    assert queued is None
