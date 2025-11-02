import json
from collections.abc import Awaitable, Callable, Iterable

import pytest

from qmtl.services.dagmanager.kafka_admin import compute_key, partition_key
from qmtl.services.gateway.commit_log import CommitLogWriter
from qmtl.services.gateway.commit_log_consumer import (
    CommitLogConsumer,
    CommitLogDeduplicator,
)


class _FakeMessage:
    def __init__(self, value: bytes) -> None:
        self.value = value


class _RecordingProducer:
    def __init__(self) -> None:
        self.messages: list[tuple[str, bytes, bytes, tuple[tuple[str, bytes], ...]]] = []
        self.begin_called = 0
        self.commit_called = 0
        self.abort_called = 0

    async def begin_transaction(self) -> None:
        self.begin_called += 1

    async def send_and_wait(
        self,
        topic: str,
        *,
        key: bytes,
        value: bytes,
        headers: Iterable[tuple[str, bytes]] | None = None,
    ) -> None:
        hdrs = tuple(headers or ())
        self.messages.append((topic, key, value, hdrs))

    async def commit_transaction(self) -> None:
        self.commit_called += 1

    async def abort_transaction(self) -> None:
        self.abort_called += 1


class _ReplayableConsumer:
    def __init__(
        self,
        payloads: list[bytes],
        *,
        batch_size: int = 1,
        start_at: int = 0,
    ) -> None:
        self._payloads = list(payloads)
        self._batch_size = max(1, batch_size)
        self._index = max(0, start_at)
        self.started = False
        self.stopped = False
        self.commit_calls = 0

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    def _next_batch(self) -> list[_FakeMessage]:
        if self._index >= len(self._payloads):
            return []
        end = min(len(self._payloads), self._index + self._batch_size)
        batch = [
            _FakeMessage(self._payloads[idx]) for idx in range(self._index, end)
        ]
        self._index = end
        return batch

    async def getmany(self, timeout_ms: int | None = None):  # noqa: D401 - signature parity
        batch = self._next_batch()
        return {} if not batch else {None: batch}

    async def commit(self) -> None:
        self.commit_calls += 1

    @property
    def exhausted(self) -> bool:
        return self._index >= len(self._payloads)


async def _drain_consumer(
    consumer: CommitLogConsumer,
    fake: _ReplayableConsumer,
    handler: Callable[[list[tuple[str, int, str, dict]]], Awaitable[None]],
) -> None:
    await consumer.start()
    try:
        while not fake.exhausted:
            await consumer.consume(handler)
    finally:
        await consumer.stop()


def _values_from_messages(
    recorded: list[tuple[str, bytes, bytes, tuple[tuple[str, bytes], ...]]]
) -> list[bytes]:
    return [value for _, _, value, _ in recorded]


@pytest.mark.asyncio
async def test_replay_determinism_and_resume_from_offset() -> None:
    producer = _RecordingProducer()
    writer = CommitLogWriter(producer, "commit-log")
    ck = compute_key("node-1", partition="A")

    original_records = [
        ("node-1", "hash-1", {"value": 1}, ck),
        ("node-1", "hash-2", {"value": 2}, ck),
        ("node-2", "hash-9", {"value": 9}, None),
    ]

    await writer.publish_bucket(1_700_000_000, 60, original_records)

    assert producer.begin_called == 1
    assert producer.commit_called == 1
    assert producer.abort_called == 0

    payloads = _values_from_messages(producer.messages)

    async def collect_records(
        *,
        batch_size: int,
        start_at: int = 0,
    ) -> list[tuple[str, int, str, dict[str, int]]]:
        fake = _ReplayableConsumer(payloads, batch_size=batch_size, start_at=start_at)
        consumer = CommitLogConsumer(
            fake,
            topic="commit-log",
            group_id="g1",
        )
        seen: list[tuple[str, int, str, dict[str, int]]] = []

        async def handler(records: list[tuple[str, int, str, dict[str, int]]]) -> None:
            seen.extend(records)

        await _drain_consumer(consumer, fake, handler)
        return seen

    first_pass = await collect_records(batch_size=2)
    second_pass = await collect_records(batch_size=1)
    resumed = await collect_records(batch_size=3, start_at=1)

    assert first_pass == second_pass
    assert resumed == first_pass[1:]


@pytest.mark.asyncio
async def test_deduplication_survives_consumer_restart_with_persisted_state() -> None:
    producer = _RecordingProducer()
    writer = CommitLogWriter(producer, "commit-log")
    ck = compute_key("node-x")

    await writer.publish_bucket(
        99,
        None,
        [
            ("node-x", "dup", {"n": 1}, ck),
        ],
    )

    payloads = _values_from_messages(producer.messages)
    dedup = CommitLogDeduplicator(ttl=60.0)

    async def run_once() -> list[tuple[str, int, str, dict[str, int]]]:
        fake = _ReplayableConsumer(payloads, batch_size=1)
        consumer = CommitLogConsumer(
            fake,
            topic="commit-log",
            group_id="g-dedup",
            deduplicator=dedup,
        )
        seen: list[tuple[str, int, str, dict[str, int]]] = []

        async def handler(records: list[tuple[str, int, str, dict[str, int]]]) -> None:
            seen.extend(records)

        await _drain_consumer(consumer, fake, handler)
        return seen

    first = await run_once()
    restart = await run_once()

    assert first == [("node-x", 99, "dup", {"n": 1})]
    assert restart == []


@pytest.mark.asyncio
async def test_partition_key_and_payload_encoding_are_stable() -> None:
    producer = _RecordingProducer()
    writer = CommitLogWriter(producer, "commit-log")

    ck_a = compute_key("node-a", execution_domain="prod", partition="0")

    bucket_ts = 1_111
    interval = 15
    await writer.publish_bucket(
        bucket_ts,
        interval,
        [
            ("node-a", "hash-1", {"x": 1}, ck_a),
            ("node-a", "hash-2", {"x": 2}, ck_a),
            ("node-b", "hash-9", {"y": 9}, None),
        ],
    )

    assert producer.begin_called == 1
    assert producer.commit_called == 1

    expected_key_prefix = partition_key(
        "node-a", interval, bucket_ts, compute_key=ck_a
    )

    keys = [key.decode() for _, key, _, _ in producer.messages]
    payloads = [json.loads(value.decode()) for _, _, value, _ in producer.messages]

    assert keys[0].startswith(expected_key_prefix)
    assert keys[1].startswith(expected_key_prefix)
    assert keys[0] != keys[1]
    assert keys[2].startswith(partition_key("node-b", interval, bucket_ts))

    assert payloads == [
        ["node-a", bucket_ts, "hash-1", {"x": 1}],
        ["node-a", bucket_ts, "hash-2", {"x": 2}],
        ["node-b", bucket_ts, "hash-9", {"y": 9}],
    ]
