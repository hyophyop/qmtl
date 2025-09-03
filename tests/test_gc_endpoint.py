from fastapi.testclient import TestClient

from qmtl.dagmanager.api import create_app
from qmtl.dagmanager.garbage_collector import QueueInfo
from datetime import datetime, UTC


class FakeGC:
    def __init__(self):
        self.calls = 0

    def collect(self):
        self.calls += 1
        return [QueueInfo("q1", "raw", datetime.now(UTC), interval="60s")]


def test_gc_route_triggers_collect():
    gc = FakeGC()
    app = create_app(gc)
    with TestClient(app) as client:
        resp = client.post("/admin/gc-trigger", json={"id": "s"})
        assert resp.status_code == 202
        assert gc.calls == 1
        assert resp.json()["processed"] == ["q1"]




