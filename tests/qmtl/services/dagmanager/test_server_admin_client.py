from __future__ import annotations

import pytest

from qmtl.services.dagmanager.kafka_admin import TopicExistsError
from qmtl.services.dagmanager.server import TopicConfigLoader, _KafkaAdminClient


# ---------------------------------------------------------------------------
# Fakes for TopicConfigLoader
# ---------------------------------------------------------------------------
class _StubConfigResource:
    class Type:
        TOPIC = "topic"

    def __init__(self, _type: str, name: str) -> None:
        self.name = name
        self.type = _type


class _StubFuture:
    def __init__(self, entries=None, exc: Exception | None = None) -> None:
        self._entries = entries or {}
        self._exc = exc

    def result(self, timeout=None):
        if self._exc:
            raise self._exc
        return self._entries


class _StubAdminClient:
    def __init__(self, futures_by_topic: dict[str, _StubFuture]) -> None:
        self._futures_by_topic = futures_by_topic

    def describe_configs(self, resources):
        return {resource: self._futures_by_topic.get(resource.name) for resource in resources}


class _Entry:
    def __init__(self, name: str | None, value) -> None:
        self.name = name
        self.value = value


def test_attach_configs_populates_expected_entries() -> None:
    topics = {"orders": {"config": {}}, "ignore": {"config": {}}}
    entries = {
        "cleanup.policy": _Entry("cleanup.policy", "compact"),
        "empty": _Entry(None, "noop"),
    }
    loader = TopicConfigLoader(
        client=_StubAdminClient({"orders": _StubFuture(entries)}),
        config_resource_cls=_StubConfigResource,
        timeout=1.0,
    )

    loader.attach_configs(topics)

    assert topics["orders"]["config"] == {"cleanup.policy": "compact"}
    # untouched when no future provided
    assert topics["ignore"]["config"] == {}


def test_attach_configs_ignores_errors() -> None:
    topics = {"orders": {"config": {}}}
    loader = TopicConfigLoader(
        client=_StubAdminClient({"orders": _StubFuture(exc=RuntimeError("boom"))}),
        config_resource_cls=_StubConfigResource,
        timeout=1.0,
    )

    loader.attach_configs(topics)

    assert topics["orders"]["config"] == {}


# ---------------------------------------------------------------------------
# Fakes for _KafkaAdminClient
# ---------------------------------------------------------------------------
class _FakeKafkaError:
    TOPIC_ALREADY_EXISTS = "exists"

    def __init__(self, code_value=None) -> None:
        self._code_value = code_value if code_value is not None else self.TOPIC_ALREADY_EXISTS

    def code(self):
        return self._code_value


class _FakeKafkaException(Exception):
    pass


class _FakeNewTopic:
    def __init__(self, topic, num_partitions, replication_factor, config) -> None:
        self.topic = topic
        self.num_partitions = num_partitions
        self.replication_factor = replication_factor
        self.config = config


class _FakeFuture:
    def __init__(self, exc: Exception | None = None) -> None:
        self._exc = exc
        self.called = False

    def result(self, timeout=None):
        self.called = True
        if self._exc:
            raise self._exc


class _FakeAdmin:
    def __init__(self, future: _FakeFuture | None) -> None:
        self.future = future
        self.last_topics = None

    def create_topics(self, topics, request_timeout=None):
        self.last_topics = topics
        if not topics:
            return {}
        name = getattr(topics[0], "topic", None)
        return {name: self.future}


class _TestKafkaAdminClient(_KafkaAdminClient):
    def __post_init__(self) -> None:  # pragma: no cover - override to avoid imports
        pass


def _build_client(future: _FakeFuture | None) -> _TestKafkaAdminClient:
    client = _TestKafkaAdminClient("bootstrap:9092")
    client._client = _FakeAdmin(future)
    client._new_topic_cls = _FakeNewTopic
    client._kafka_exception_cls = _FakeKafkaException
    client._kafka_error_cls = _FakeKafkaError
    return client


def test_create_topic_converts_config_and_successful_flow() -> None:
    future = _FakeFuture()
    client = _build_client(future)

    client.create_topic("orders", num_partitions=3, replication_factor=2, config={"retention.ms": 60000})

    assert isinstance(client._client.last_topics[0], _FakeNewTopic)
    assert client._client.last_topics[0].config == {"retention.ms": "60000"}
    assert future.called is True


def test_create_topic_raises_topic_exists() -> None:
    future = _FakeFuture(_FakeKafkaException(_FakeKafkaError(_FakeKafkaError.TOPIC_ALREADY_EXISTS)))
    client = _build_client(future)

    with pytest.raises(TopicExistsError):
        client.create_topic("orders", num_partitions=1, replication_factor=1)


def test_create_topic_propagates_unexpected_errors() -> None:
    future = _FakeFuture(ValueError("unexpected"))
    client = _build_client(future)

    with pytest.raises(ValueError):
        client.create_topic("orders", num_partitions=1, replication_factor=1)
