import pytest
from types import SimpleNamespace

from qmtl.common import compute_node_id
from qmtl.gateway.dagmanager_client import DagManagerClient


@pytest.mark.asyncio
async def test_world_scoping_changes_ids_and_topics(monkeypatch):
    data = ("T", "code", "cfg", "schema", "w1")
    nid1 = compute_node_id(*data)
    nid2 = compute_node_id("T", "code", "cfg", "schema", "w2")
    assert nid1 != nid2

    client = DagManagerClient("dummy")

    class StubTagStub:
        async def GetQueues(self, request):
            return SimpleNamespace(queues=[SimpleNamespace(**{"queue": "base", "global": False})])

    def fake_ensure(self):
        self._tag_stub = StubTagStub()
    monkeypatch.setattr(DagManagerClient, "_ensure_channel", fake_ensure)

    q1 = await client.get_queues_by_tag(["t"], 60, world_id="w1")
    q2 = await client.get_queues_by_tag(["t"], 60, world_id="w2")
    assert q1[0]["queue"] == "w/w1/base"
    assert q2[0]["queue"] == "w/w2/base"
    await client.close()
