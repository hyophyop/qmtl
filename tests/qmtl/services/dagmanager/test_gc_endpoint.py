from datetime import UTC, datetime

from fastapi.testclient import TestClient

from qmtl.services.dagmanager.api import create_app
from qmtl.services.dagmanager.garbage_collector import CleanupReport, QueueInfo


class FakeGC:
    def __init__(self):
        self.calls = 0

    def collect(self):
        self.calls += 1
        return [QueueInfo("q1", "raw", datetime.now(UTC), interval=60)]

    def collect_report(self):
        self.calls += 1
        processed = [QueueInfo("q1", "raw", datetime.now(UTC), interval=60)]
        return CleanupReport(
            observed=1,
            candidates=1,
            processed=processed,
            skipped=[],
            actions={"drop": 1, "archive": 0, "skip": 0},
            by_tag={"raw": 1},
            items=[],
        )


def test_gc_route_triggers_collect():
    gc = FakeGC()
    app = create_app(gc)
    with TestClient(app) as client:
        resp = client.post("/admin/gc-trigger", json={"id": "s"})
        assert resp.status_code == 202
        assert gc.calls == 1
        assert resp.json()["processed"] == ["q1"]
        assert resp.json()["report"]["actions"] == {"drop": 1, "archive": 0, "skip": 0}



