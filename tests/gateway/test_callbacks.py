from fastapi.testclient import TestClient

from qmtl.gateway.api import create_app
from qmtl.gateway import metrics
from qmtl.gateway.ws import WebSocketHub
from qmtl.gateway import metrics
from qmtl.common.cloudevents import format_event


def test_dag_event_route():
    app = create_app()
    client = TestClient(app)
    event = format_event("test", "diff", {})
    resp = client.post("/callbacks/dag-event", json=event)
    assert resp.status_code == 202
    assert resp.json()["ok"] is True


def test_dag_event_sentinel_weight():
    class DummyHub:
        def __init__(self):
            self.weights = []

        async def send_sentinel_weight(self, sid: str, weight: float) -> None:
            self.weights.append((sid, weight))

    hub = DummyHub()
    app = create_app(ws_hub=hub)
    client = TestClient(app)
    metrics.reset_metrics()
    event = format_event(
        "qmtl.dagmanager",
        "sentinel_weight",
        {"sentinel_id": "v1", "weight": 0.7},
    )
    resp = client.post("/callbacks/dag-event", json=event)
    assert resp.status_code == 202
    assert hub.weights == [("v1", 0.7)]
    assert metrics.gateway_sentinel_traffic_ratio._vals["v1"] == 0.7


def test_dag_event_sentinel_weight_metric():
    class DummyHub:
        def __init__(self):
            self.weights = []

        async def send_sentinel_weight(self, sid: str, weight: float) -> None:
            self.weights.append((sid, weight))

    metrics.reset_metrics()
    hub = DummyHub()
    app = create_app(ws_hub=hub)
    client = TestClient(app)
    event = format_event(
        "qmtl.dagmanager",
        "sentinel_weight",
        {"sentinel_id": "v2", "weight": 0.5},
    )
    resp = client.post("/callbacks/dag-event", json=event)
    assert resp.status_code == 202
    assert hub.weights == [("v2", 0.5)]
    assert (
        metrics.gateway_sentinel_traffic_ratio.labels("v2")._value.get() == 0.5
    )


def test_dag_event_sentinel_weight_invalid():
    class DummyHub:
        def __init__(self):
            self.weights = []

        async def send_sentinel_weight(self, sid: str, weight: float) -> None:
            self.weights.append((sid, weight))

    metrics.reset_metrics()
    hub = DummyHub()
    app = create_app(ws_hub=hub)
    client = TestClient(app)
    event = format_event(
        "qmtl.dagmanager",
        "sentinel_weight",
        {"sentinel_id": "v3", "weight": 1.2},
    )
    resp = client.post("/callbacks/dag-event", json=event)
    assert resp.status_code == 202
    assert hub.weights == []
    assert ("v3",) not in metrics.gateway_sentinel_traffic_ratio._metrics
