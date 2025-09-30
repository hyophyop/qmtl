import asyncio
import pytest

from qmtl.foundation.common import AsyncCircuitBreaker
from qmtl.services.dagmanager import metrics
from qmtl.services.dagmanager.kafka_admin import KafkaAdmin, TopicExistsError
from qmtl.services.dagmanager.topic import TopicConfig


class FailingAdmin:
    def __init__(self, fail_times: int) -> None:
        self.fail_times = fail_times
        self.calls = 0
        self.topics = {}

    def list_topics(self):
        return self.topics

    def create_topic(self, name, *, num_partitions, replication_factor, config=None):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("boom")
        if name in self.topics:
            raise TopicExistsError
        self.topics[name] = {
            "config": dict(config or {}),
            "num_partitions": num_partitions,
            "replication_factor": replication_factor,
        }


class ExistsAdmin:
    def __init__(self) -> None:
        self.topics = {"t": {}}

    def list_topics(self):
        return self.topics

    def create_topic(self, name, *, num_partitions, replication_factor, config=None):
        if name in self.topics:
            raise TopicExistsError
        self.topics[name] = {
            "config": dict(config or {}),
            "num_partitions": num_partitions,
            "replication_factor": replication_factor,
        }


class FlakyCreateAdmin:
    def __init__(self) -> None:
        self.calls = 0
        self.topics: dict[str, dict] = {}

    def list_topics(self):
        return self.topics

    def create_topic(self, name, *, num_partitions, replication_factor, config=None):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient")
        self.topics[name] = {
            "config": dict(config or {}),
            "num_partitions": num_partitions,
            "replication_factor": replication_factor,
        }


class ConflictingAdmin:
    def list_topics(self):
        return {
            "t": {
                "num_partitions": 2,
                "replication_factor": 1,
                "config": {"retention.ms": "999"},
            }
        }

    def create_topic(self, name, *, num_partitions, replication_factor, config=None):
        raise TopicExistsError


@pytest.mark.asyncio
async def test_circuit_breaker_opens_on_failures():
    client = FailingAdmin(fail_times=2)
    admin = KafkaAdmin(
        client,
        breaker=AsyncCircuitBreaker(max_failures=2),
        max_attempts=1,
        wait_initial=0.0,
        wait_max=0.0,
    )
    cfg = TopicConfig(1, 1, 1000)
    metrics.reset_metrics()

    with pytest.raises(RuntimeError):
        await asyncio.to_thread(admin.create_topic_if_needed, "t", cfg)
    with pytest.raises(RuntimeError):
        await asyncio.to_thread(admin.create_topic_if_needed, "t", cfg)
    assert admin.breaker.is_open
    assert metrics.kafka_breaker_open_total._value.get() == 1  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError):
        await asyncio.to_thread(admin.create_topic_if_needed, "t", cfg)
    admin.breaker.reset()
    await asyncio.to_thread(admin.create_topic_if_needed, "t", cfg)
    assert not admin.breaker.is_open


@pytest.mark.asyncio
async def test_custom_on_open_preserved():
    triggered = False

    def custom_hook() -> None:
        nonlocal triggered
        triggered = True

    breaker = AsyncCircuitBreaker(
        max_failures=1,
        on_open=custom_hook,
    )
    admin = KafkaAdmin(
        FailingAdmin(fail_times=1),
        breaker=breaker,
        max_attempts=1,
        wait_initial=0.0,
        wait_max=0.0,
    )
    cfg = TopicConfig(1, 1, 1000)
    metrics.reset_metrics()

    with pytest.raises(RuntimeError):
        await asyncio.to_thread(admin.create_topic_if_needed, "t", cfg)

    assert triggered
    assert metrics.kafka_breaker_open_total._value.get() == 1  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_topic_exists_does_not_trip_breaker():
    client = ExistsAdmin()
    admin = KafkaAdmin(
        client,
        breaker=AsyncCircuitBreaker(max_failures=1),
        max_attempts=2,
        wait_initial=0.0,
        wait_max=0.0,
    )
    cfg = TopicConfig(1, 1, 1000)

    await asyncio.to_thread(admin.create_topic_if_needed, "t", cfg)
    assert admin.breaker.failures == 0


@pytest.mark.asyncio
async def test_create_topic_succeeds_after_retry():
    admin = KafkaAdmin(
        FlakyCreateAdmin(),
        breaker=AsyncCircuitBreaker(max_failures=3),
        max_attempts=3,
        wait_initial=0.0,
        wait_max=0.0,
    )
    cfg = TopicConfig(1, 1, 123)

    await asyncio.to_thread(admin.create_topic_if_needed, "t", cfg)
    assert admin.client.topics["t"]["config"]["retention.ms"] == "123"


@pytest.mark.asyncio
async def test_name_collision_raises_topic_exists():
    admin = KafkaAdmin(
        ConflictingAdmin(),
        breaker=AsyncCircuitBreaker(max_failures=1),
        max_attempts=1,
        wait_initial=0.0,
        wait_max=0.0,
    )
    cfg = TopicConfig(1, 1, 1000)

    with pytest.raises(TopicExistsError):
        await asyncio.to_thread(admin.create_topic_if_needed, "t", cfg)
