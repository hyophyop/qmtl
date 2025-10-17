from __future__ import annotations

import pytest

from qmtl.services.dagmanager.kafka_admin import compute_key
from qmtl.services.gateway.commit_log import CommitLogWriter
from qmtl.services.gateway.commit_log_consumer import CommitLogConsumer

from tests.qmtl.services.service_doubles import (
    FakeKafkaMessage,
    RecordingCommitLogConsumerBackend,
    RecordingCommitLogProducer,
)


@pytest.mark.asyncio
async def test_commit_log_consumer_deduplicates_batches_contract():
    producer = RecordingCommitLogProducer()
    writer = CommitLogWriter(producer, "commit.topic")

    compute_hint = compute_key("n1")
    await writer.publish_bucket(
        100,
        60,
        [("n1", "ih", {"v": i % 3}, compute_hint) for i in range(6)],
    )

    assert producer.began == 1
    assert producer.committed == 1

    batch = [FakeKafkaMessage(msg["value"]) for msg in producer.messages]
    backend = RecordingCommitLogConsumerBackend([batch])
    consumer = CommitLogConsumer(backend, topic="commit.topic", group_id="group-1")

    observed: list[tuple[str, int, str, object]] = []

    async def handler(records):
        observed.extend(records)

    await consumer.start()
    await consumer.consume(handler)
    await consumer.stop()

    assert backend.commit_calls == 1
    assert [record[0] for record in observed] == ["n1"]
    assert [record[1] for record in observed] == [100]
    assert [record[2] for record in observed] == ["ih"]
    assert [record[3] for record in observed] == [{"v": 0}]
