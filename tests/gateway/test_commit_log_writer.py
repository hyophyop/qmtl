import json
import pytest

from qmtl.dagmanager.kafka_admin import partition_key
from qmtl.gateway.commit_log import CommitLogWriter
from qmtl.sdk.node import NodeCache


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

    await writer.publish_bucket(120, 60, [("n1", h, {"a": 1})])

    assert producer.begin_called == 1
    assert producer.commit_called == 1
    assert producer.abort_called == 0
    assert producer.messages[0][0] == "commit-log"
    expected_key = f"{partition_key('n1', 60, 120)}:{h}".encode()
    assert producer.messages[0][1] == expected_key
    assert json.loads(producer.messages[0][2].decode()) == ["n1", 120, h, {"a": 1}]


@pytest.mark.asyncio
async def test_publish_bucket_aborts_on_error() -> None:
    class ErrProducer(FakeProducer):
        async def send_and_wait(self, topic: str, key: bytes, value: bytes) -> None:  # pragma: no cover - deterministic
            raise RuntimeError("boom")

    producer = ErrProducer()
    writer = CommitLogWriter(producer, "commit-log")

    with pytest.raises(RuntimeError):
        await writer.publish_bucket(200, 60, [("n1", "h1", "x")])

    assert producer.begin_called == 1
    assert producer.commit_called == 0
    assert producer.abort_called == 1
