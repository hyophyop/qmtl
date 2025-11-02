from __future__ import annotations

from types import SimpleNamespace

import pytest

from qmtl.foundation.common import compute_node_id
from qmtl.services.dagmanager import topic as topic_module
from qmtl.services.gateway.dagmanager_client import DagManagerClient


class RecordingTagStub:
    """Fake TagQuery stub capturing the requests made by the client."""

    def __init__(self, queues: list[SimpleNamespace]):
        self._queues = queues
        self.requests = []

    async def GetQueues(self, request):  # pragma: no cover - exercised via tests
        self.requests.append(request)
        return SimpleNamespace(queues=self._queues)


class StubbedDagManagerClient(DagManagerClient):
    """Client variant that avoids gRPC channel creation for tests."""

    def __init__(self, tag_stub: RecordingTagStub):
        super().__init__("unused-test-target")
        self._tag_stub = tag_stub
        self.ensure_calls = 0

    def _ensure_channel(self) -> None:  # pragma: no cover - exercised via tests
        # ``get_queues_by_tag`` always ensures the channel before executing the
        # RPC. Counting invocations confirms the collaboration contract without
        # touching real network primitives.
        self.ensure_calls += 1


@pytest.fixture
def restore_topic_namespace():
    original = topic_module.topic_namespace_enabled()
    yield
    topic_module.set_topic_namespace_enabled(original)


def _make_queue(name: str) -> SimpleNamespace:
    return SimpleNamespace(**{"queue": name, "global": False})


def test_compute_node_id_is_deterministic_for_equivalent_payloads() -> None:
    payload = {
        "node_type": "T",
        "code_hash": "code",
        "config_hash": "cfg",
        "schema_hash": "schema",
        "schema_compat_id": "schema-major",
        "interval": 10,
        "period": 2,
        "params": {
            "alpha": 1,
            "nested": {"beta": 2, "gamma": [3, 1, 2]},
            "zeta": 0,
        },
        "dependencies": ["dep-a", "dep-b"],
    }
    reordered = {
        **payload,
        "params": {
            "zeta": 0,
            "nested": {"gamma": [3, 1, 2], "beta": 2},
            "alpha": 1,
        },
        "dependencies": list(reversed(payload["dependencies"])),
    }

    assert compute_node_id(payload) == compute_node_id(reordered)


@pytest.mark.asyncio
async def test_get_queues_by_tag_applies_world_namespace(restore_topic_namespace):
    topic_module.set_topic_namespace_enabled(True)
    stub = RecordingTagStub([_make_queue("base")])
    client = StubbedDagManagerClient(stub)

    queues = await client.get_queues_by_tag(
        ["latency"],
        60,
        world_id="w1",
        execution_domain="dryrun",
    )

    assert queues == [{"queue": "w1.dryrun.base", "global": False}]
    assert stub.requests, "RPC request should be captured"
    request = stub.requests[0]
    assert list(request.tags) == ["latency"]
    assert request.interval == 60
    assert request.match_mode == "any"
    assert client.ensure_calls == 1
    await client.close()


@pytest.mark.asyncio
async def test_get_queues_by_tag_defaults_to_live_namespace(restore_topic_namespace):
    topic_module.set_topic_namespace_enabled(True)
    stub = RecordingTagStub([_make_queue("primary")])
    client = StubbedDagManagerClient(stub)

    queues = await client.get_queues_by_tag(["fills"], 15, world_id="prod-world")

    assert queues == [{"queue": "prod-world.live.primary", "global": False}]
    await client.close()
