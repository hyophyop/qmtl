import pytest

from qmtl.dagmanager.kafka_admin import compute_key
from qmtl.gateway import metrics
from qmtl.gateway.commit_log import CommitLogWriter
from qmtl.gateway.commit_log_consumer import CommitLogConsumer


class FakeProducer:
    def __init__(self) -> None:
        self.messages: list[tuple[str, bytes, bytes]] = []
        self.begin_called = 0
        self.commit_called = 0
        self.abort_called = 0
        self.stopped = False

    async def begin_transaction(self) -> None:
        self.begin_called += 1

    async def send_and_wait(self, topic: str, key: bytes, value: bytes) -> None:
        self.messages.append((topic, key, value))

    async def commit_transaction(self) -> None:
        self.commit_called += 1

    async def abort_transaction(self) -> None:
        self.abort_called += 1

    async def stop(self) -> None:
        self.stopped = True


class _FakeMessage:
    def __init__(self, value: bytes) -> None:
        self.value = value


class _FakeConsumer:
    def __init__(self, batches: list[list[_FakeMessage]]) -> None:
        self._batches = list(batches)
        self.started = False
        self.stopped = False
        self.commit_calls = 0

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def getmany(self, timeout_ms: int | None = None):
        if self._batches:
            return {None: self._batches.pop(0)}
        return {}

    async def commit(self) -> None:
        self.commit_calls += 1


@pytest.mark.asyncio
async def test_commit_log_end_to_end() -> None:
    metrics.reset_metrics()
    producer = FakeProducer()
    writer = CommitLogWriter(producer, "commit-log")

    # duplicate record within a batch
    ck = compute_key("n1")
    await writer.publish_bucket(
        100,
        60,
        [("n1", "h1", {"a": 1}, ck), ("n1", "h1", {"a": 2}, ck)],
    )

    # consumer reads messages produced above
    batch = [_FakeMessage(value) for _, _, value in producer.messages]
    consumer = _FakeConsumer([batch])
    cl_consumer = CommitLogConsumer(consumer, topic="commit-log", group_id="g1")

    received: list[tuple[str, int, str, dict[str, int]]] = []

    async def handler(records: list[tuple[str, int, str, dict[str, int]]]) -> None:
        received.extend(records)

    await cl_consumer.start()
    await cl_consumer.consume(handler)
    await cl_consumer.stop()
    await producer.stop()

    assert received == [("n1", 100, "h1", {"a": 1})]
    assert metrics.commit_duplicate_total._value.get() == 1
    assert consumer.commit_calls == 1
    assert producer.stopped
