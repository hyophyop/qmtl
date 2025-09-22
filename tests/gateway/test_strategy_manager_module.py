import base64
import hashlib
import json
from datetime import datetime
from typing import Any

import pytest
from fastapi import HTTPException

from qmtl.gateway import metrics
from qmtl.gateway.commit_log import CommitLogWriter
from qmtl.gateway.database import MemoryDatabase
from qmtl.gateway.fsm import StrategyFSM
from qmtl.gateway.models import StrategySubmit
from qmtl.gateway.redis_client import InMemoryRedis
from qmtl.gateway.strategy_manager import StrategyManager


@pytest.mark.asyncio
async def test_strategy_manager_submit_and_status():
    redis = InMemoryRedis()
    db = MemoryDatabase()
    fsm = StrategyFSM(redis=redis, database=db)
    manager = StrategyManager(redis=redis, database=db, fsm=fsm, insert_sentinel=False)

    dag = {"nodes": []}
    payload = StrategySubmit(
        dag_json=base64.b64encode(json.dumps(dag).encode()).decode(),
        meta=None,
        node_ids_crc32=0,
    )
    sid, existed = await manager.submit(payload)
    assert not existed
    assert await manager.status(sid) == "queued"


class RecordingProducer:
    def __init__(self) -> None:
        self.records: list[tuple[str, bytes, bytes, Any]] = []

    async def begin_transaction(self) -> None:
        return None

    async def send_and_wait(
        self,
        topic: str,
        *,
        key: bytes | None = None,
        value: bytes | None = None,
        headers: Any | None = None,
    ) -> None:
        self.records.append((topic, key or b"", value or b"", headers))

    async def commit_transaction(self) -> None:
        return None

    async def abort_transaction(self) -> None:
        return None


@pytest.mark.asyncio
async def test_strategy_manager_writes_commit_log() -> None:
    metrics.reset_metrics()
    redis = InMemoryRedis()
    db = MemoryDatabase()
    fsm = StrategyFSM(redis=redis, database=db)
    producer = RecordingProducer()
    writer = CommitLogWriter(producer, "gateway.ingest")
    manager = StrategyManager(
        redis=redis,
        database=db,
        fsm=fsm,
        insert_sentinel=True,
        commit_log_writer=writer,
    )

    dag = {
        "nodes": [
            {
                "node_id": "n1",
                "node_type": "TypeA",
                "config_hash": "c",
                "code_hash": "d",
                "schema_hash": "s",
                "schema_compat_id": "s-major",
                "params": {},
                "dependencies": [],
            }
        ]
    }
    dag_json = base64.b64encode(json.dumps(dag).encode()).decode()
    payload = StrategySubmit(
        dag_json=dag_json,
        meta={
            "execution_domain": " live ",
            "as_of": "2024-01-02T00:00:00Z",
            "partition": "p0",
            "dataset_fingerprint": "abc123",
            "other": 5,
        },
        world_id="world-main",
        world_ids=["world-main", "world-shadow"],
        node_ids_crc32=0,
    )

    expected_hash = hashlib.sha256(json.dumps(dag, sort_keys=True).encode()).hexdigest()

    sid, existed = await manager.submit(payload)
    assert not existed
    assert sid
    assert await manager.status(sid) == "queued"
    assert producer.records, "commit log should record the submission"
    topic, key, value, headers = producer.records[0]
    assert topic == "gateway.ingest"
    assert key == f"ingest:{sid}".encode()
    record = json.loads(value.decode())
    assert record[0] == "gateway.ingest"
    assert record[2] == sid
    submission = record[3]
    assert submission["strategy_id"] == sid
    assert submission["dag_hash"] == expected_hash
    assert submission["node_ids_crc32"] == 0
    assert submission["world_ids"] == ["world-main", "world-shadow"]
    assert submission["compute_context"] == {
        "world_id": "world-main",
        "execution_domain": "live",
        "as_of": "2024-01-02T00:00:00Z",
        "partition": "p0",
        "dataset_fingerprint": "abc123",
    }
    assert submission.get("world_id") == "world-main"
    assert submission["insert_sentinel"] is True
    # dag_base64 should round-trip to the stored dag (with sentinel appended)
    stored_dag = json.loads(base64.b64decode(submission["dag_base64"]).decode())
    assert stored_dag == submission["dag"]
    assert any(node.get("node_type") == "VersionSentinel" for node in submission["dag"].get("nodes", []))
    # submitted_at must be ISO formatted
    datetime.fromisoformat(submission["submitted_at"])  # will raise if invalid
    assert metrics.lost_requests_total._value.get() == 0


class ExplodingProducer:
    async def begin_transaction(self) -> None:
        return None

    async def send_and_wait(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("producer failure")

    async def commit_transaction(self) -> None:
        return None

    async def abort_transaction(self) -> None:
        return None


@pytest.mark.asyncio
async def test_strategy_manager_rollback_on_commit_log_failure() -> None:
    metrics.reset_metrics()
    redis = InMemoryRedis()
    db = MemoryDatabase()
    fsm = StrategyFSM(redis=redis, database=db)
    writer = CommitLogWriter(ExplodingProducer(), "gateway.ingest")
    manager = StrategyManager(
        redis=redis,
        database=db,
        fsm=fsm,
        insert_sentinel=False,
        commit_log_writer=writer,
    )

    dag = {"nodes": []}
    dag_json = base64.b64encode(json.dumps(dag).encode()).decode()
    payload = StrategySubmit(
        dag_json=dag_json,
        meta=None,
        world_id=None,
        node_ids_crc32=0,
    )

    with pytest.raises(HTTPException) as excinfo:
        await manager.submit(payload)

    assert excinfo.value.status_code == 503
    # dedupe keys should be removed to keep submission idempotent
    hash_key = hashlib.sha256(json.dumps(dag, sort_keys=True).encode()).hexdigest()
    assert await redis.get(f"dag_hash:{hash_key}") is None
    assert metrics.lost_requests_total._value.get() == 1
