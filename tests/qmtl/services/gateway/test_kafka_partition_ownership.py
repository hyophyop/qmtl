from collections import deque

import pytest

from qmtl.services.gateway.ownership import KafkaPartitionOwnership


class _StubPartition:
    def __init__(self, topic: str, partition: int) -> None:
        self.topic = topic
        self.partition = partition


class _StubConsumer:
    def __init__(
        self,
        topic: str,
        partitions: set[int],
        assignments: list[set[int]],
    ) -> None:
        self._topic = topic
        self._partitions = partitions
        self._assignments = deque(assignments)
        self.start_calls = 0

    async def start(self) -> None:
        self.start_calls += 1

    def partitions_for_topic(self, topic: str):
        assert topic == self._topic
        return self._partitions

    def assignment(self):
        current = self._assignments[0] if self._assignments else set()
        if len(self._assignments) > 1:
            current = self._assignments.popleft()
        return {_StubPartition(self._topic, partition) for partition in current}


@pytest.mark.asyncio
async def test_acquire_succeeds_when_assigned_partition() -> None:
    consumer = _StubConsumer(
        topic="gateway.ownership",
        partitions={0, 1},
        assignments=[{1}],
    )
    owner = KafkaPartitionOwnership(
        consumer,
        "gateway.ownership",
        rebalance_attempts=1,
        rebalance_backoff=0,
    )

    assert await owner.acquire(5)
    assert consumer.start_calls == 1


@pytest.mark.asyncio
async def test_acquire_waits_for_assignment_before_checking() -> None:
    consumer = _StubConsumer(
        topic="gateway.ownership",
        partitions={0, 1},
        assignments=[set(), {1}],
    )
    owner = KafkaPartitionOwnership(
        consumer,
        "gateway.ownership",
        rebalance_attempts=2,
        rebalance_backoff=0,
    )

    assert await owner.acquire(3)
    assert consumer.start_calls == 1


@pytest.mark.asyncio
async def test_acquire_returns_false_when_partition_unassigned() -> None:
    consumer = _StubConsumer(
        topic="gateway.ownership",
        partitions={0, 1},
        assignments=[{0}],
    )
    owner = KafkaPartitionOwnership(
        consumer,
        "gateway.ownership",
        rebalance_attempts=1,
        rebalance_backoff=0,
    )

    assert await owner.acquire(3) is False
    assert consumer.start_calls == 1

