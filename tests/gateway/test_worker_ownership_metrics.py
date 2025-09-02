import asyncio
from collections import deque

import pytest

from qmtl.gateway import metrics
from qmtl.gateway.commit_log import CommitLogWriter
from qmtl.gateway.commit_log_consumer import CommitLogConsumer
from qmtl.gateway.database import PostgresDatabase
from qmtl.gateway.ownership import OwnershipManager


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
async def test_worker_takeover_increments_reassign_metric_once() -> None:
    metrics.reset_metrics()
    conn = FakeConn()
    db = PostgresDatabase("dsn")
    db._pool = FakePool(conn)  # type: ignore[assignment]
    manager = OwnershipManager(db)

    producer = FakeProducer()
    writer = CommitLogWriter(producer, "commit-log")

    key = 456

    async def owning_worker() -> None:
        acquired = await manager.acquire(key, owner="w1")
        assert acquired
        try:
            await asyncio.sleep(0.1)
        finally:
            await manager.release(key)

    task = asyncio.create_task(owning_worker())
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    async def takeover_worker() -> None:
        acquired = await manager.acquire(key, owner="w2")
        assert acquired
        try:
            await writer.publish_bucket(200, 60, [("n1", "h2", {"b": 2})])
        finally:
            await manager.release(key)

    await takeover_worker()
    assert len(producer.messages) == 1

    batch = [_FakeMessage(value) for _, _, value in producer.messages]
    consumer = _FakeConsumer([batch])
    cl_consumer = CommitLogConsumer(consumer, topic="commit", group_id="g1")

    received: list[tuple[str, int, str, dict[str, int]]] = []

    async def handler(records: list[tuple[str, int, str, dict[str, int]]]) -> None:
        received.extend(records)

    await cl_consumer.consume(handler)

    assert received == [("n1", 200, "h2", {"b": 2})]
    assert metrics.commit_duplicate_total._value.get() == 0
    assert metrics.owner_reassign_total._value.get() == 1
