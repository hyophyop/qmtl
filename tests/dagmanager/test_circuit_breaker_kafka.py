import asyncio
import pytest

from qmtl.foundation.common import AsyncCircuitBreaker
from qmtl.services.dagmanager.kafka_admin import KafkaAdmin, TopicExistsError
from qmtl.services.dagmanager import metrics
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
        self.topics[name] = {}


class ExistsAdmin:
    def __init__(self) -> None:
        self.topics = {"t": {}}

    def list_topics(self):
        return self.topics

    def create_topic(self, name, *, num_partitions, replication_factor, config=None):
        if name in self.topics:
            raise TopicExistsError
        self.topics[name] = {}


@pytest.mark.asyncio
async def test_circuit_breaker_opens_on_failures():
    client = FailingAdmin(fail_times=2)
    admin = KafkaAdmin(client, breaker=AsyncCircuitBreaker(max_failures=2))
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
    admin = KafkaAdmin(FailingAdmin(fail_times=1), breaker=breaker)
    cfg = TopicConfig(1, 1, 1000)
    metrics.reset_metrics()

    with pytest.raises(RuntimeError):
        await asyncio.to_thread(admin.create_topic_if_needed, "t", cfg)

    assert triggered
    assert metrics.kafka_breaker_open_total._value.get() == 1  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_topic_exists_does_not_trip_breaker():
    client = ExistsAdmin()
    admin = KafkaAdmin(client, breaker=AsyncCircuitBreaker(max_failures=1))
    cfg = TopicConfig(1, 1, 1000)

    await asyncio.to_thread(admin.create_topic_if_needed, "t", cfg)
    assert admin.breaker.failures == 0
