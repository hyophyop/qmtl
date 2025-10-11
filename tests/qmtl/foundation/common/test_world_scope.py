import pytest
from types import SimpleNamespace

from qmtl.foundation.common import compute_node_id
from qmtl.services.gateway.dagmanager_client import DagManagerClient
import qmtl.services.dagmanager.topic as topic_module


@pytest.mark.asyncio
async def test_world_scoping_topics(monkeypatch):
    data = {
        "node_type": "T",
        "code_hash": "code",
        "config_hash": "cfg",
        "schema_hash": "schema",
        "schema_compat_id": "schema-major",
        "interval": 10,
        "period": 2,
        "params": {"k": 1},
        "dependencies": [],
    }
    nid1 = compute_node_id(data)
    nid2 = compute_node_id(data)
    assert nid1 == nid2

    client = DagManagerClient("dummy")

    class StubTagStub:
        async def GetQueues(self, request):
            return SimpleNamespace(queues=[SimpleNamespace(**{"queue": "base", "global": False})])

    def fake_ensure(self):
        self._tag_stub = StubTagStub()
    monkeypatch.setattr(DagManagerClient, "_ensure_channel", fake_ensure)

    monkeypatch.setattr(topic_module, "_NAMESPACE_ENABLED", True)

    q1 = await client.get_queues_by_tag(["t"], 60, world_id="w1", execution_domain="dryrun")
    q2 = await client.get_queues_by_tag(["t"], 60, world_id="w2", execution_domain="dryrun")
    assert q1[0]["queue"] == "w1.dryrun.base"
    assert q2[0]["queue"] == "w2.dryrun.base"
    await client.close()
