import json
import base64
import pytest
from fastapi.testclient import TestClient
from fakeredis.aioredis import FakeRedis
import asyncio

from qmtl.gateway.watch import QueueWatchHub

from qmtl.gateway.api import create_app, Database
from qmtl.gateway.dagmanager_client import DagManagerClient
from qmtl.dagmanager.grpc_server import serve
from qmtl.dagmanager.diff_service import StreamSender
import grpc


class _FakeSession:
    def __init__(self, result=None):
        self.result = result or []

    def run(self, query, **params):
        return self.result

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass


class _FakeDriver:
    def __init__(self, result=None):
        self.session_obj = _FakeSession(result)

    def session(self):
        return self.session_obj


class _FakeAdmin:
    def __init__(self, topics=None):
        self.topics = topics or {}

    def list_topics(self):
        return self.topics

    def create_topic(self, name, *, num_partitions, replication_factor, config=None):
        pass


class _FakeStream(StreamSender):
    def send(self, chunk):
        pass

    def wait_for_ack(self):
        pass

    def ack(self):
        pass


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


@pytest.mark.asyncio
async def test_watch_hub_broadcast():
    hub = QueueWatchHub()

    async def listen():
        gen = hub.subscribe(["t1"], 60)
        try:
            return await asyncio.wait_for(gen.__anext__(), 2.0)
        except asyncio.TimeoutError:
            pytest.fail("Timeout occurred while waiting for broadcast")
        finally:
            await gen.aclose()

    task = asyncio.create_task(listen())
    await asyncio.sleep(0)
    await hub.broadcast(["t1"], 60, ["q3"])
    try:
        result = await task
        assert result == ["q3"]
    except asyncio.CancelledError:
        pytest.fail("Task was unexpectedly cancelled")


@pytest.mark.asyncio
async def test_dag_client_queries_grpc():
    driver = _FakeDriver([{"topic": "q1"}, {"topic": "q2"}])
    admin = _FakeAdmin()
    stream = _FakeStream()
    server, port = serve(driver, admin, stream, host="127.0.0.1", port=0)
    await server.start()
    client = DagManagerClient(f"127.0.0.1:{port}")
    queues = await client.get_queues_by_tag(["t"], 60)
    await server.stop(None)
    assert queues == ["q1", "q2"]
