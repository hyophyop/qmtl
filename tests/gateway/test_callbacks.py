from fastapi.testclient import TestClient

from qmtl.gateway.api import create_app
from qmtl.common.cloudevents import format_event


def test_dag_event_route():
    app = create_app()
    client = TestClient(app)
    event = format_event("test", "diff", {})
    resp = client.post("/callbacks/dag-event", json=event)
    assert resp.status_code == 202
    assert resp.json()["ok"] is True
