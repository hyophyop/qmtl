import json
import pytest

from qmtl.services.dagmanager.kafka_admin import partition_key, compute_key
from qmtl.services.gateway.commit_log import CommitLogWriter
from qmtl.runtime.sdk.node import NodeCache


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


@pytest.mark.asyncio
async def test_publish_bucket_commits() -> None:
    producer = FakeProducer()
    writer = CommitLogWriter(producer, "commit-log")

    cache = NodeCache(period=2)
    cache.append("u1", 60, 60, {"v": 1})
    cache.append("u1", 60, 120, {"v": 2})
    h = cache.input_window_hash()

    await writer.publish_bucket(120, 60, [("n1", h, {"a": 1}, compute_key("n1"))])

    assert producer.begin_called == 1
    assert producer.commit_called == 1
    assert producer.abort_called == 0
    assert producer.messages[0][0] == "commit-log"
    expected_key = f"{partition_key('n1', 60, 120, compute_key=compute_key('n1'))}:{h}".encode()
    assert producer.messages[0][1] == expected_key
    assert json.loads(producer.messages[0][2].decode()) == ["n1", 120, h, {"a": 1}]


@pytest.mark.asyncio
@pytest.mark.parametrize("compute_hint", [None, compute_key("n1")])
async def test_publish_bucket_key_layout_is_stable(compute_hint: str | None) -> None:
    """The message key should match ``"{partition_key}:{input_hash}"`` from the docs."""

    producer = FakeProducer()
    writer = CommitLogWriter(producer, "commit-log")

    cache = NodeCache(period=2)
    cache.append("u1", 60, 60, {"v": 1})
    cache.append("u1", 60, 120, {"v": 2})
    h = cache.input_window_hash()

    if compute_hint is None:
        records = [("n1", h, {"a": 1})]
    else:
        records = [("n1", h, {"a": 1}, compute_hint)]

    await writer.publish_bucket(120, 60, records)

    assert producer.messages, "publish_bucket should emit a Kafka record"
    key = producer.messages[0][1].decode()
    prefix = partition_key("n1", 60, 120, compute_key=compute_hint)

    assert key == f"{prefix}:{h}"
    # Split on the final colon so compute-key decorations remain part of the prefix.
    observed_prefix, observed_hash = key.rsplit(":", 1)
    assert observed_prefix == prefix
    assert observed_hash == h


@pytest.mark.asyncio
async def test_publish_bucket_aborts_on_error() -> None:
    class ErrProducer(FakeProducer):
        async def send_and_wait(self, topic: str, key: bytes, value: bytes) -> None:  # pragma: no cover - deterministic
            raise RuntimeError("boom")

    producer = ErrProducer()
    writer = CommitLogWriter(producer, "commit-log")

    with pytest.raises(RuntimeError):
        await writer.publish_bucket(200, 60, [("n1", "h1", "x", compute_key("n1"))])

    assert producer.begin_called == 1
    assert producer.commit_called == 0
    assert producer.abort_called == 1


@pytest.mark.asyncio
async def test_publish_submission_formats_payload() -> None:
    producer = FakeProducer()
    writer = CommitLogWriter(producer, "commit-log")

    await writer.publish_submission(
        "strategy-1",
        {"dag_hash": "h", "node_ids_crc32": 123},
        timestamp_ms=1690000000000,
    )

    assert producer.messages, "submission should emit a commit-log record"
    topic, key, value = producer.messages[0]
    assert topic == "commit-log"
    assert key == b"ingest:strategy-1"
    record = json.loads(value.decode())
    assert record[0] == "gateway.ingest"
    assert record[1] == 1690000000000
    assert record[2] == "strategy-1"
    assert record[3] == {"dag_hash": "h", "node_ids_crc32": 123}
