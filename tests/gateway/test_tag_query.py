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
