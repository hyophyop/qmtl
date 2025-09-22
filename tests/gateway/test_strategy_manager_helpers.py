import base64
import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from qmtl.gateway import metrics
from qmtl.gateway.database import MemoryDatabase
from qmtl.gateway.degradation import DegradationLevel
from qmtl.gateway.fsm import StrategyFSM
from qmtl.gateway.models import StrategySubmit
from qmtl.gateway.redis_client import InMemoryRedis
from qmtl.gateway.strategy_manager import StrategyManager


@pytest.fixture
def strategy_manager() -> StrategyManager:
    redis = InMemoryRedis()
    db = MemoryDatabase()
    fsm = StrategyFSM(redis=redis, database=db)
    return StrategyManager(redis=redis, database=db, fsm=fsm, insert_sentinel=True)


def _make_payload(meta: dict | None = None) -> StrategySubmit:
    dag = {"nodes": [{"node_id": "n1", "node_type": "X"}]}
    dag_json = base64.b64encode(json.dumps(dag).encode()).decode()
    return StrategySubmit(dag_json=dag_json, meta=meta or {}, node_ids_crc32=0)


def test_decode_dag_adds_sentinel(strategy_manager: StrategyManager) -> None:
    payload = _make_payload({"version": " 1.2.3 "})

    decoded = strategy_manager._decode_dag(payload)

    assert decoded.strategy_id
    assert decoded.dag_for_storage is not decoded.dag
    sentinel = decoded.dag_for_storage["nodes"][-1]
    assert sentinel["node_type"] == "VersionSentinel"
    assert sentinel["node_id"].endswith("-sentinel")
    assert sentinel["version"] == "1.2.3"
    round_tripped = json.loads(base64.b64decode(decoded.encoded_dag).decode())
    assert round_tripped == decoded.dag_for_storage


def test_decode_dag_accepts_plain_json(strategy_manager: StrategyManager) -> None:
    dag = {"nodes": []}
    payload = StrategySubmit(
        dag_json=json.dumps(dag),
        meta={},
        node_ids_crc32=0,
    )

    decoded = strategy_manager._decode_dag(payload)

    assert decoded.dag == dag
    assert json.loads(base64.b64decode(decoded.encoded_dag).decode())["nodes"]


@pytest.mark.asyncio
async def test_ensure_unique_strategy_detects_duplicates(
    strategy_manager: StrategyManager,
) -> None:
    payload = _make_payload()
    decoded = strategy_manager._decode_dag(payload)

    first_id, existed = await strategy_manager._ensure_unique_strategy(
        decoded.strategy_id, decoded.dag_hash, decoded.encoded_dag
    )

    assert not existed
    assert first_id == decoded.strategy_id

    duplicate_id, existed = await strategy_manager._ensure_unique_strategy(
        str(uuid.uuid4()), decoded.dag_hash, decoded.encoded_dag
    )

    assert existed is True
    assert duplicate_id == first_id


@pytest.mark.asyncio
async def test_publish_submission_noop_without_writer(
    strategy_manager: StrategyManager,
) -> None:
    payload = _make_payload()
    decoded = strategy_manager._decode_dag(payload)
    _, compute_ctx_payload, _, worlds = strategy_manager._build_compute_context(payload)

    await strategy_manager._publish_submission(
        decoded.strategy_id,
        decoded.dag_for_storage,
        decoded.encoded_dag,
        decoded.dag_hash,
        payload,
        compute_ctx_payload,
        worlds,
    )


class _ExplodingWriter:
    async def publish_submission(self, strategy_id: str, record: dict) -> None:  # pragma: no cover - signature docs
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_publish_submission_failure_rolls_back(
    strategy_manager: StrategyManager,
) -> None:
    metrics.reset_metrics()
    payload = _make_payload()
    decoded = strategy_manager._decode_dag(payload)
    await strategy_manager._ensure_unique_strategy(
        decoded.strategy_id, decoded.dag_hash, decoded.encoded_dag
    )

    strategy_manager.commit_log_writer = _ExplodingWriter()
    _, compute_ctx_payload, _, worlds = strategy_manager._build_compute_context(payload)

    with pytest.raises(HTTPException):
        await strategy_manager._publish_submission(
            decoded.strategy_id,
            decoded.dag_for_storage,
            decoded.encoded_dag,
            decoded.dag_hash,
            payload,
            compute_ctx_payload,
            worlds,
        )

    assert await strategy_manager.redis.get(f"dag_hash:{decoded.dag_hash}") is None
    assert metrics.lost_requests_total._value.get() == 1


@pytest.mark.asyncio
async def test_enqueue_strategy_respects_degradation(
    strategy_manager: StrategyManager,
) -> None:
    payload = _make_payload()
    decoded = strategy_manager._decode_dag(payload)

    degrade = SimpleNamespace(
        level=DegradationLevel.PARTIAL,
        dag_ok=False,
        local_queue=[],
    )
    strategy_manager.degrade = degrade

    await strategy_manager._enqueue_strategy(decoded.strategy_id)
    assert degrade.local_queue == [decoded.strategy_id]

    degrade.level = DegradationLevel.NORMAL
    degrade.dag_ok = True
    await strategy_manager._enqueue_strategy(decoded.strategy_id)
    queued = await strategy_manager.redis.lpop("strategy_queue")
    assert queued == decoded.strategy_id
