import asyncio
import pytest

from qmtl.gateway.commit_log_consumer import CommitLogDeduplicator
from qmtl.gateway import metrics


def test_commit_log_deduplicator_filters_duplicates():
    metrics.reset_metrics()
    dedup = CommitLogDeduplicator()
    records = [
        ("n1", 100, "h1", {"a": 1}),
        ("n1", 100, "h1", {"a": 2}),  # duplicate
        ("n1", 100, "h2", {"a": 3}),
    ]
    out = list(dedup.filter(records))
    assert out == [
        ("n1", 100, "h1", {"a": 1}),
        ("n1", 100, "h2", {"a": 3}),
    ]
    # second batch should drop already seen key
    more = list(dedup.filter([( "n1", 100, "h1", {"a": 4})]))
    assert more == []
    assert metrics.commit_duplicate_total._value.get() == 2


@pytest.mark.asyncio
async def test_concurrent_workers_single_commit() -> None:
    metrics.reset_metrics()
    log: list[tuple[str, int, str, dict[str, int]]] = []

    async def worker(record: tuple[str, int, str, dict[str, int]], delay: float) -> None:
        await asyncio.sleep(delay)
        log.append(record)

    r1 = ("n1", 100, "h1", {"a": 1})
    r2 = ("n1", 100, "h1", {"a": 2})
    await asyncio.gather(worker(r1, 0), worker(r2, 0.01))

    dedup = CommitLogDeduplicator()
    out = list(dedup.filter(log))
    assert out == [r1]
    assert metrics.commit_duplicate_total._value.get() == 1


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
