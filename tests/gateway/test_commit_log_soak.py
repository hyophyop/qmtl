import asyncio
from collections import deque

import pytest

from qmtl.gateway.commit_log import CommitLogWriter
from qmtl.gateway.commit_log_consumer import CommitLogConsumer
from qmtl.gateway.ownership import OwnershipManager
from qmtl.gateway.database import PostgresDatabase


class FakeConn:
    def __init__(self) -> None:
        self.locked: set[int] = set()

    async def fetchval(self, query: str, key: int) -> bool:
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

    def acquire(self):
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

    async def getmany(self, timeout_ms: int | None = None):
        if self._batches:
            return {None: self._batches.popleft()}
        return {}

    async def commit(self) -> None:
        self.commit_calls += 1


@pytest.mark.asyncio
async def test_exactly_once_multi_round_soak() -> None:
    rounds = 10
    conn = FakeConn()
    db = PostgresDatabase("dsn")
    db._pool = FakePool(conn)  # type: ignore[assignment]
    manager = OwnershipManager(db)

    producer = FakeProducer()
    writer = CommitLogWriter(producer, "commit-log")

    async def one_round(idx: int) -> None:
        key = 1000 + idx

        async def worker(owner: str) -> bool:
            if not await manager.acquire(key, owner=owner):
                return False
            try:
                await asyncio.sleep(0.005)
                await writer.publish_bucket(100 + idx, 60, [("n1", f"h{idx}", {"v": idx})])
                return True
            finally:
                await manager.release(key)

        # Race two workers for the same key
        r1, r2 = await asyncio.gather(worker("w1"), worker("w2"))
        assert (r1 or r2) and not (r1 and r2), "exactly one worker should win per round"

    await asyncio.gather(*[one_round(i) for i in range(rounds)])

    # Build a single batch of all produced messages
    batch = [_FakeMessage(value) for _, _, value in producer.messages]
    consumer = _FakeConsumer([batch])
    cl_consumer = CommitLogConsumer(consumer, topic="commit", group_id="g1")

    received: list[tuple[str, int, str, dict[str, int]]] = []

    async def handler(records: list[tuple[str, int, str, dict[str, int]]]) -> None:
        received.extend(records)

    await cl_consumer.consume(handler)

    # We should receive exactly one record per round
    assert len(received) == rounds

