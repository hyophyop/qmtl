import json
import base64
import pytest
from fastapi.testclient import TestClient
from fakeredis.aioredis import FakeRedis

from qmtl.gateway.api import create_app, Database
from qmtl.gateway.dagmanager_client import DagManagerClient


class FakeDB(Database):
    async def insert_strategy(self, strategy_id: str, meta=None):
        pass

    async def set_status(self, strategy_id: str, status: str) -> None:
        pass

    async def get_status(self, strategy_id: str):
        return None

    async def append_event(self, strategy_id: str, event: str) -> None:  # pragma: no cover - not used
        pass


class DummyDag(DagManagerClient):
    def __init__(self):
        super().__init__("dummy")
        self.called_with = None

    async def get_queues_by_tag(self, tags, interval):
        self.called_with = (tags, interval)
        return ["q1", "q2"]


@pytest.fixture
def client():
    redis = FakeRedis(decode_responses=True)
    dag = DummyDag()
    app = create_app(redis_client=redis, database=FakeDB(), dag_client=dag)
    return TestClient(app), dag


def test_queues_by_tag_route(client):
    c, dag = client
    resp = c.get("/queues/by_tag", params={"tags": "t1,t2", "interval": "60"})
    assert resp.status_code == 200
    assert resp.json()["queues"] == ["q1", "q2"]
    assert dag.called_with == (["t1", "t2"], 60)


def test_submit_tag_query_node(client):
    c, dag = client
    dag_json = {
        "nodes": [
            {
                "node_id": "N1",
                "node_type": "TagQueryNode",
                "interval": 60,
                "period": 2,
                "tags": ["t1"],
                "code_hash": "ch",
                "schema_hash": "sh",
                "inputs": [],
            }
        ]
    }
    payload = {
        "dag_json": base64.b64encode(json.dumps(dag_json).encode()).decode(),
        "meta": None,
        "run_type": "dry-run",
    }
    resp = c.post("/strategies", json=payload)
    assert resp.status_code == 202
    assert resp.json()["queue_map"] == {"N1": ["q1", "q2"]}
    assert dag.called_with == (["t1"], 60)
