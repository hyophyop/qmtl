import asyncio
import logging

import pytest

from types import SimpleNamespace

from qmtl.services.gateway.redis_queue import RedisTaskQueue
from qmtl.services.gateway.worker import StrategyWorker
from qmtl.services.gateway.database import Database
from qmtl.services.gateway.fsm import StrategyFSM
from qmtl.services.gateway.ws import WebSocketHub
from qmtl.services.dagmanager.kafka_admin import partition_key, compute_key
import zlib


class DummyManager:
    def __init__(self) -> None:
        self.locked: set[int] = set()
        self.acquire_calls: list[int] = []
        self.release_calls: list[int] = []

    async def acquire(self, key: int, owner: str | None = None) -> bool:
        self.acquire_calls.append(key)
        if key in self.locked:
            return False
        self.locked.add(key)
        return True

    async def release(self, key: int) -> None:
        self.release_calls.append(key)
        self.locked.discard(key)


class FakeDB(Database):
    def __init__(self) -> None:
        self.records: dict[str, str] = {}
        self.completions: list[str] = []
        self.events: list[tuple[str, str]] = []

    async def insert_strategy(self, strategy_id: str, meta=None) -> None:  # pragma: no cover - not used
        self.records[strategy_id] = "queued"

    async def set_status(self, strategy_id: str, status: str) -> None:
        self.records[strategy_id] = status
        if status == "completed":
            self.completions.append(strategy_id)

    async def get_status(self, strategy_id: str) -> str | None:
        return self.records.get(strategy_id)

    async def append_event(self, strategy_id: str, event: str) -> None:  # pragma: no cover - not used
        self.events.append((strategy_id, event))


@pytest.mark.asyncio
async def test_worker_locking_single_processing(fake_redis):
    redis = fake_redis
    queue = RedisTaskQueue(redis, "strategy_queue")
    db = FakeDB()
    fsm = StrategyFSM(redis, db)
    manager = DummyManager()

    await fsm.create("sid", None)
    await redis.hset("strategy:sid", mapping={"dag": "{}"})

    await queue.push("sid")

    async def diff(sid: str, dag: str, **_kwargs):
        return SimpleNamespace(queue_map={}, sentinel_id="s")

    dag_client = SimpleNamespace(diff=diff)

    w1 = StrategyWorker(redis, db, fsm, queue, dag_client, ws_hub=None, manager=manager)
    w2 = StrategyWorker(redis, db, fsm, queue, dag_client, ws_hub=None, manager=manager)

    results = await asyncio.gather(w1.run_once(), w2.run_once())

    assert results.count("sid") == 1
    assert db.completions.count("sid") == 1
    assert db.records["sid"] == "completed"
    expected_key = zlib.crc32(partition_key("sid", None, None).encode())
    assert manager.acquire_calls == [expected_key]
    assert manager.release_calls == [expected_key]


class DummyHub(WebSocketHub):
    def __init__(self) -> None:
        super().__init__()
        self.progress: list[tuple[str, str]] = []
        self.maps: list[tuple[str, dict]] = []

    async def send_progress(self, strategy_id: str, status: str) -> None:  # type: ignore[override]
        self.progress.append((strategy_id, status))

    async def send_queue_map(self, strategy_id: str, queue_map: dict[str, list[str] | str]) -> None:  # type: ignore[override]
        self.maps.append((strategy_id, queue_map))


@pytest.mark.asyncio
async def test_worker_diff_success_broadcasts(fake_redis):
    redis = fake_redis
    queue = RedisTaskQueue(redis, "strategy_queue")
    db = FakeDB()
    fsm = StrategyFSM(redis, db)

    await fsm.create("sid", None)
    await redis.hset("strategy:sid", mapping={"dag": "{}"})
    await queue.push("sid")

    called = []

    async def diff(sid: str, dag: str, **_kwargs):
        called.append((sid, dag))
        return SimpleNamespace(
            queue_map={
                partition_key(
                    "n",
                    None,
                    None,
                    compute_key=compute_key("n"),
                ): "t"
            },
            sentinel_id="s",
        )

    dag_client = SimpleNamespace(diff=diff)
    hub = DummyHub()
    worker = StrategyWorker(redis, db, fsm, queue, dag_client, hub, manager=DummyManager())
    await worker.run_once()

    assert called == [("sid", "{}")]
    assert hub.maps == [
        ("sid", {partition_key("n", None, None, compute_key=compute_key("n")): "t"})
    ]
    assert hub.progress[0] == ("sid", "processing")
    assert hub.progress[-1] == ("sid", "completed")
    assert db.records["sid"] == "completed"


@pytest.mark.asyncio
async def test_worker_diff_failure_sets_failed_and_broadcasts(fake_redis):
    redis = fake_redis
    queue = RedisTaskQueue(redis, "strategy_queue")
    db = FakeDB()
    fsm = StrategyFSM(redis, db)

    await fsm.create("sid", None)
    await redis.hset("strategy:sid", mapping={"dag": "{}"})
    await queue.push("sid")

    called = []

    async def diff(sid: str, dag: str, **_kwargs):
        called.append((sid, dag))
        raise RuntimeError("fail")

    dag_client = SimpleNamespace(diff=diff)
    hub = DummyHub()
    worker = StrategyWorker(redis, db, fsm, queue, dag_client, hub, manager=DummyManager())
    await worker.run_once()

    assert called == [("sid", "{}")]
    assert hub.maps == []
    assert hub.progress[0] == ("sid", "processing")
    assert hub.progress[-1] == ("sid", "failed")
    assert db.records["sid"] == "failed"


@pytest.mark.asyncio
async def test_process_logs_diff_error(fake_redis, caplog):
    redis = fake_redis
    queue = RedisTaskQueue(redis, "strategy_queue")
    db = FakeDB()
    fsm = StrategyFSM(redis, db)

    await fsm.create("sid", None)
    await redis.hset("strategy:sid", mapping={"dag": "{}"})

    async def diff(sid: str, dag: str, **_kwargs):
        raise RuntimeError("fail")

    dag_client = SimpleNamespace(diff=diff)
    worker = StrategyWorker(redis, db, fsm, queue, dag_client, ws_hub=None, manager=DummyManager())

    caplog.set_level(logging.ERROR)
    result = await worker._process("sid")

    assert result is False
    assert "gRPC diff failed for strategy sid" in caplog.text
    assert db.records["sid"] == "failed"


@pytest.mark.asyncio
async def test_process_logs_unhandled_error(fake_redis, caplog):
    redis = fake_redis
    queue = RedisTaskQueue(redis, "strategy_queue")
    db = FakeDB()
    fsm = StrategyFSM(redis, db)

    await fsm.create("sid", None)
    await redis.hset("strategy:sid", mapping={"dag": "{}"})

    async def diff(sid: str, dag: str, **_kwargs):
        return SimpleNamespace(queue_map={}, sentinel_id="s")

    async def handler(sid: str):
        raise RuntimeError("boom")

    dag_client = SimpleNamespace(diff=diff)
    worker = StrategyWorker(
        redis,
        db,
        fsm,
        queue,
        dag_client,
        ws_hub=None,
        handler=handler,
        manager=DummyManager(),
    )

    caplog.set_level(logging.ERROR)
    result = await worker._process("sid")

    assert result is False
    assert "Unhandled error processing strategy sid" in caplog.text
    assert db.records["sid"] == "failed"

