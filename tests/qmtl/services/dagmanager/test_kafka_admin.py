from __future__ import annotations

from qmtl.services.dagmanager.server import _KafkaAdminClient


class FakeKafkaError:
    NO_ERROR = 0


class _Error:
    def __init__(self, code: int):
        self._code = code

    def code(self) -> int:
        return self._code


class _Partition:
    def __init__(self, replicas: list[int] | None):
        self.replicas = replicas or []


class _Topic:
    def __init__(self, *, partitions: dict[int, _Partition], error: _Error | None = None):
        self.partitions = partitions
        if error is not None:
            self.error = error


class _Metadata:
    def __init__(self, topics: dict[str, _Topic]):
        self.topics = topics


class _ConfigResource:
    class Type:
        TOPIC = "topic"

    def __init__(self, resource_type, name):  # pragma: no cover - trivial
        self.resource_type = resource_type
        self.name = name


class _AdminClient:
    def __init__(self, metadata: _Metadata, *, futures=None, raise_on_describe: Exception | None = None):
        self._metadata = metadata
        self._futures = futures or {}
        self._raise_on_describe = raise_on_describe

    def list_topics(self, timeout: float) -> _Metadata:  # pragma: no cover - trivial
        return self._metadata

    def describe_configs(self, resources):  # pragma: no cover - trivial
        if self._raise_on_describe:
            raise self._raise_on_describe
        return self._futures


def _make_admin(metadata: _Metadata) -> _KafkaAdminClient:
    admin = _KafkaAdminClient(bootstrap_servers="unused")
    admin._client = _AdminClient(metadata)
    admin._config_resource_cls = None
    admin._kafka_error_cls = FakeKafkaError
    return admin


def test_list_topics_skips_error_topics() -> None:
    metadata = _Metadata(
        topics={
            "ok": _Topic(partitions={0: _Partition([1, 2])}, error=_Error(FakeKafkaError.NO_ERROR)),
            "errored": _Topic(
                partitions={0: _Partition([1])},
                error=_Error(1),
            ),
        }
    )
    admin = _make_admin(metadata)

    topics = admin.list_topics()

    assert "ok" in topics
    assert topics["ok"]["num_partitions"] == 1
    assert topics["ok"]["replication_factor"] == 2
    assert "errored" not in topics


def test_list_topics_returns_empty_config_when_config_resource_missing() -> None:
    metadata = _Metadata(topics={"topic": _Topic(partitions={})})
    admin = _make_admin(metadata)

    topics = admin.list_topics()

    assert topics["topic"]["config"] == {}


def test_list_topics_handles_describe_failure_gracefully() -> None:
    metadata = _Metadata(topics={"topic": _Topic(partitions={0: _Partition([1])})})
    admin = _KafkaAdminClient(bootstrap_servers="unused")
    admin._client = _AdminClient(metadata, raise_on_describe=RuntimeError("boom"))
    admin._config_resource_cls = _ConfigResource
    admin._kafka_error_cls = FakeKafkaError

    topics = admin.list_topics()

    assert topics["topic"]["config"] == {}
