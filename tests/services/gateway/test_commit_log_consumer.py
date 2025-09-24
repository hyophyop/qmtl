import asyncio
import json
from collections import deque

import pytest

from qmtl.services.gateway.commit_log_consumer import CommitLogConsumer, CommitLogDeduplicator
from qmtl.services.gateway import metrics


def test_commit_log_deduplicator_filters_duplicates_and_ttl():
    metrics.reset_metrics()
    dedup = CommitLogDeduplicator(maxsize=128, ttl=0.01)
    first = ("n1", 100, "h1", {"a": 1})
    dup = ("n1", 100, "h1", {"a": 2})
    third = ("n1", 100, "h2", {"a": 3})
    out = list(dedup.filter([first, dup, third]))
    assert out == [first, third]
    # second batch should drop already seen key
    more = list(dedup.filter([( "n1", 100, "h1", {"a": 4})]))
    assert more == []
    assert metrics.commit_duplicate_total._value.get() == 2
    # after TTL expires the key is processed again
    dedup._seen.expire(dedup._seen.timer() + 0.02)
    again = list(dedup.filter([( "n1", 100, "h1", {"a": 5})]))
    assert again == [("n1", 100, "h1", {"a": 5})]


def test_commit_log_deduplicator_evicts_old_keys():
    metrics.reset_metrics()
    dedup = CommitLogDeduplicator(maxsize=2, ttl=60.0)
    r1 = ("n1", 100, "h1", {"a": 1})
    r2 = ("n1", 100, "h2", {"a": 2})
    r3 = ("n1", 100, "h3", {"a": 3})
    assert list(dedup.filter([r1])) == [r1]
    assert list(dedup.filter([r1])) == []
    assert metrics.commit_duplicate_total._value.get() == 1
    assert list(dedup.filter([r2, r3])) == [r2, r3]
    assert list(dedup.filter([r1])) == [r1]


@pytest.mark.asyncio
async def test_concurrent_workers_single_commit() -> None:
    metrics.reset_metrics()
    log: list[tuple[str, int, str, dict[str, int]]] = []

    async def worker(record: tuple[str, int, str, dict[str, int]], start: asyncio.Event) -> None:
        await start.wait()
        log.append(record)

    start = asyncio.Event()
    r1 = ("n1", 100, "h1", {"a": 1})
    r2 = ("n1", 100, "h1", {"a": 2})
    t1 = asyncio.create_task(worker(r1, start))
    t2 = asyncio.create_task(worker(r2, start))
    start.set()
    await asyncio.gather(t1, t2)

    dedup = CommitLogDeduplicator()
    out = list(dedup.filter(log))
    assert out == [r1]
    assert metrics.commit_duplicate_total._value.get() == 1


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
async def test_commit_log_consumer_dedup_and_metrics() -> None:
    metrics.reset_metrics()

    r1 = ("n1", 100, "h1", {"a": 1})
    r2 = ("n1", 100, "h2", {"a": 2})
    r3 = ("n1", 100, "h3", {"a": 3})

    def _enc(record: tuple[str, int, str, dict[str, int]]) -> _FakeMessage:
        return _FakeMessage(json.dumps(record).encode())

    batches = [
        [_enc(r1), _enc(r1), _enc(r2)],  # duplicate r1
        [_enc(r1), _enc(r3)],  # r1 duplicate again
    ]

    fake_consumer = _FakeConsumer(batches)
    cl_consumer = CommitLogConsumer(fake_consumer, topic="commit", group_id="g1")

    received: list[list[tuple[str, int, str, dict[str, int]]]] = []

    async def handler(records: list[tuple[str, int, str, dict[str, int]]]) -> None:
        received.append(records)

    await cl_consumer.consume(handler)
    await cl_consumer.consume(handler)

    assert received == [[r1, r2], [r3]]
    assert metrics.commit_duplicate_total._value.get() == 2
    assert fake_consumer.commit_calls == 2


@pytest.mark.asyncio
async def test_owner_reassign_emits_one_additional_commit() -> None:
    metrics.reset_metrics()
    dedup = CommitLogDeduplicator()

    first = ("n1", 100, "h1", {"a": 1})
    out1 = list(dedup.filter([first]))
    assert out1 == [first]

    # Reassigned worker processes the same bucket again
    second_batch = [
        ("n1", 100, "h1", {"a": 1}),  # duplicate of first
        ("n1", 100, "h2", {"a": 2}),  # new commit
    ]
    out2 = list(dedup.filter(second_batch))

    assert out2 == [("n1", 100, "h2", {"a": 2})]
    assert metrics.commit_duplicate_total._value.get() == 1


@pytest.mark.asyncio
async def test_commit_log_consumer_ignores_invalid_messages() -> None:
    metrics.reset_metrics()

    valid = ("n1", 100, "h1", {"a": 1})
    bad_msg = _FakeMessage(b"{invalid")
    good_msg = _FakeMessage(json.dumps(valid).encode())

    fake_consumer = _FakeConsumer([[bad_msg, good_msg]])
    cl_consumer = CommitLogConsumer(fake_consumer, topic="commit", group_id="g1")

    received: list[list[tuple[str, int, str, dict[str, int]]]] = []

    async def handler(records: list[tuple[str, int, str, dict[str, int]]]) -> None:
        received.append(records)

    await cl_consumer.consume(handler)

    assert received == [[valid]]
    assert metrics.commit_invalid_total._value.get() == 1
