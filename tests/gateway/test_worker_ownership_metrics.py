import asyncio
import zlib
from collections import deque
from types import SimpleNamespace

import pytest

from qmtl.gateway import metrics
from qmtl.gateway.commit_log import CommitLogWriter
from qmtl.gateway.commit_log_consumer import CommitLogConsumer
from qmtl.gateway.database import PostgresDatabase, Database
from qmtl.gateway.ownership import OwnershipManager
from qmtl.gateway.redis_queue import RedisTaskQueue
from qmtl.gateway.worker import StrategyWorker
from qmtl.gateway.fsm import StrategyFSM
from qmtl.dagmanager.kafka_admin import partition_key


class FakeConn:
    def __init__(self) -> None:
        self.locked: set[int] = set()
        self.calls: list[tuple[str, int]] = []

    async def fetchval(self, query: str, key: int) -> bool:
        self.calls.append((query, key))
        if "pg_try_advisory_lock" in query:
            if key in self.locked:
                return False
            self.locked.add(key)
            return True
        if "pg_advisory_unlock" in query:
            self.locked.discard(key)
            return True
        return True


class FakePool:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn

    def acquire(self):  # noqa: D401 - test shim
        conn = self.conn

        class _Ctx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, exc_type, exc, tb):
                return None

        return _Ctx()


class FakeProducer:
    def __init__(self) -> None:
        self.messages: list[tuple[str, bytes, bytes]] = []
        self.begin_called = 0
        self.commit_called = 0
        self.abort_called = 0

    async def begin_transaction(self) -> None:
        self.begin_called += 1

    async def send_and_wait(self, topic: str, key: bytes, value: bytes) -> None:
        self.messages.append((topic, key, value))

    async def commit_transaction(self) -> None:
        self.commit_called += 1

    async def abort_transaction(self) -> None:
        self.abort_called += 1


class _FakeMessage:
    def __init__(self, value: bytes) -> None:
        self.value = value


class _FakeConsumer:
    def __init__(self, batches: list[list[_FakeMessage]]) -> None:
        self._batches: deque[list[_FakeMessage]] = deque(batches)
        self.commit_calls = 0

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def getmany(self, timeout_ms: int | None = None):  # noqa: D401 - test shim
        if self._batches:
            return {None: self._batches.popleft()}
        return {}

    async def commit(self) -> None:
        self.commit_calls += 1


class FakeDB(Database):
    def __init__(self) -> None:
        self.records: dict[str, str] = {}

    async def insert_strategy(self, strategy_id: str, meta=None) -> None:
        self.records[strategy_id] = "queued"

    async def set_status(self, strategy_id: str, status: str) -> None:
        self.records[strategy_id] = status

    async def get_status(self, strategy_id: str) -> str | None:
        return self.records.get(strategy_id)

    async def append_event(self, strategy_id: str, event: str) -> None:
        return None


@pytest.mark.asyncio
async def test_two_workers_single_commit_no_duplicates() -> None:
    metrics.reset_metrics()
    conn = FakeConn()
    db = PostgresDatabase("dsn")
    db._pool = FakePool(conn)  # type: ignore[assignment]
    manager = OwnershipManager(db)

    producer = FakeProducer()
    writer = CommitLogWriter(producer, "commit-log")

    key = 123

    async def worker() -> bool:
        if not await manager.acquire(key):
            return False
        try:
            await asyncio.sleep(0.05)
            await writer.publish_bucket(100, 60, [("n1", "h1", {"a": 1})])
            return True
        finally:
            await manager.release(key)

    results = await asyncio.gather(worker(), worker())
    assert results.count(True) == 1
    assert len(producer.messages) == 1

    batch = [_FakeMessage(value) for _, _, value in producer.messages]
    consumer = _FakeConsumer([batch])
    cl_consumer = CommitLogConsumer(consumer, topic="commit", group_id="g1")

    received: list[tuple[str, int, str, dict[str, int]]] = []

    async def handler(records: list[tuple[str, int, str, dict[str, int]]]) -> None:
        received.extend(records)

    await cl_consumer.consume(handler)

    assert received == [("n1", 100, "h1", {"a": 1})]
    assert metrics.commit_duplicate_total._value.get() == 0


@pytest.mark.asyncio
async def test_worker_takeover_increments_reassign_metric_once(fake_redis) -> None:
    metrics.reset_metrics()
    conn = FakeConn()
    lock_db = PostgresDatabase("dsn")
    lock_db._pool = FakePool(conn)  # type: ignore[assignment]
    manager = OwnershipManager(lock_db)

    redis = fake_redis
    queue = RedisTaskQueue(redis, "strategy_queue")
    db = FakeDB()
    fsm = StrategyFSM(redis, db)

    async def diff(sid: str, dag: str):
        return SimpleNamespace(queue_map={}, sentinel_id="s")

    dag_client = SimpleNamespace(diff=diff)
    worker = StrategyWorker(
        redis, db, fsm, queue, dag_client, ws_hub=None, manager=manager
    )

    strategy_id = "sid"
    await fsm.create(strategy_id, None)
    await redis.hset(f"strategy:{strategy_id}", mapping={"dag": "{}"})
    await queue.push(strategy_id)

    key = zlib.crc32(partition_key(strategy_id, None, None).encode())
    # Simulate another worker currently holding the key so acquisition fails
    assert await manager.acquire(key)

    # First attempt fails and item is requeued
    result = await worker.run_once()
    assert result is None

    await manager.release(key)

    # Second attempt succeeds and triggers the reassignment metric
    result = await worker.run_once()
    assert result == strategy_id
    assert metrics.owner_reassign_total._value.get() == 1
