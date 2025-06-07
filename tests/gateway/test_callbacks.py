from fastapi.testclient import TestClient

from qmtl.gateway.api import create_app


def test_dag_event_route():
    app = create_app()
    client = TestClient(app)
    resp = client.post("/callbacks/dag-event", json={"event": "diff"})
    assert resp.status_code == 202
    assert resp.json()["ok"] is True
