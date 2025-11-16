from __future__ import annotations

import asyncio
import pytest

from qmtl.services.dagmanager.kafka_admin import (
    InMemoryAdminClient,
    KafkaAdmin,
    TopicEnsureResult,
    TopicExistsError,
    TopicVerificationPolicy,
)
from qmtl.services.dagmanager.topic import TopicConfig


class _RecordingAdmin(InMemoryAdminClient):
    def __init__(self, *, fail_creates: int = 0) -> None:
        super().__init__()
        self.fail_creates = fail_creates
        self.create_calls: list[str] = []

    def create_topic(self, name: str, *, num_partitions: int, replication_factor: int, config=None):  # type: ignore[override]
        self.create_calls.append(name)
        if self.fail_creates > 0:
            self.fail_creates -= 1
            raise RuntimeError("transient create failure")
        return super().create_topic(
            name,
            num_partitions=num_partitions,
            replication_factor=replication_factor,
            config=config,
        )


@pytest.mark.parametrize(
    "metadata",
    [
        {"topic": {"num_partitions": 2, "replication_factor": 1, "config": {"retention.ms": "100"}}},
        {"topic": {"num_partitions": "2", "replication_factor": "1", "config": {"retention.ms": "100"}}},
    ],
)
def test_verification_policy_accepts_matching_metadata(metadata):
    policy = TopicVerificationPolicy()
    config = TopicConfig(partitions=2, replication_factor=1, retention_ms=100)

    result = policy.evaluate("topic", metadata, config)

    assert isinstance(result, TopicEnsureResult)
    assert result.ok
    assert result.error is None
    assert result.diagnostics.get("reason") == "verified"


def test_verification_policy_detects_collisions():
    policy = TopicVerificationPolicy()
    metadata = {"Topic": {}, "topic": {}}

    result = policy.evaluate("topic", metadata, TopicConfig(1, 1, 1))

    assert not result.ok
    assert isinstance(result.error, TopicExistsError)
    assert "Topic" in result.collisions


@pytest.mark.parametrize(
    "metadata",
    [
        {"topic": {"num_partitions": 1}},
        {"topic": {"replication_factor": 5}},
        {"topic": {"config": {"retention.ms": "999"}}},
    ],
)
def test_verification_policy_reports_parameter_mismatch(metadata):
    policy = TopicVerificationPolicy()
    config = TopicConfig(partitions=2, replication_factor=3, retention_ms=1000)

    result = policy.evaluate("topic", metadata, config)

    assert not result.ok
    assert isinstance(result.error, TopicExistsError)


@pytest.mark.asyncio
async def test_create_topic_retries_and_raises_last_error():
    client = _RecordingAdmin(fail_creates=2)
    admin = KafkaAdmin(
        client,
        max_attempts=2,
        wait_initial=0.0,
        wait_max=0.0,
        backoff_multiplier=1.0,
    )

    config = TopicConfig(1, 1, 100)

    with pytest.raises(RuntimeError):
        await asyncio.to_thread(admin.create_topic_if_needed, "t", config)

    assert client.create_calls == ["t", "t"]


@pytest.mark.asyncio
async def test_create_topic_succeeds_after_missing_metadata_then_create():
    client = _RecordingAdmin(fail_creates=1)
    admin = KafkaAdmin(
        client,
        max_attempts=3,
        wait_initial=0.0,
        wait_max=0.0,
        backoff_multiplier=1.0,
    )
    config = TopicConfig(1, 1, 10)

    await asyncio.to_thread(admin.create_topic_if_needed, "topic", config)

    assert "topic" in client.list_topics()
    assert client.create_calls == ["topic", "topic"]
