from datetime import datetime
from fastapi.testclient import TestClient

from qmtl.gateway.api import create_app as gw_create_app
from qmtl.dagmanager.http_server import create_app as dag_http_create_app
from qmtl.dagmanager.api import create_app as dag_api_create_app
from qmtl.dagmanager.gc import QueueInfo


class DummyGC:
    def collect(self):
        return [QueueInfo("q", "raw", datetime.utcnow(), interval=60)]


def test_gateway_health():
    client = TestClient(gw_create_app())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_dagmanager_http_health():
    client = TestClient(dag_http_create_app())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_dagmanager_api_health():
    client = TestClient(dag_api_create_app(DummyGC()))
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
