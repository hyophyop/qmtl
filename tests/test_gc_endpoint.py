from fastapi.testclient import TestClient
import httpx

from qmtl.dagmanager.api import create_app
from qmtl.dagmanager.gc import QueueInfo
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


def test_gc_route_emits_callback(monkeypatch):
    gc = FakeGC()
    events = []

    async def fake_post(url, payload, **_):
        events.append((url, payload))
        return httpx.Response(202)

    monkeypatch.setattr("qmtl.dagmanager.api.post_with_backoff", fake_post)

    app = create_app(gc, callback_url="http://gw/cb")
    with TestClient(app) as client:
        client.post("/admin/gc-trigger", json={"id": "x"})

        assert events
        assert events[0][0] == "http://gw/cb"
        assert events[0][1]["type"] == "gc"
        assert events[0][1]["data"]["id"] == "x"

