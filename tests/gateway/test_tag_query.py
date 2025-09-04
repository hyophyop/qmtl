import json
import base64
import gc
import pytest
from fastapi.testclient import TestClient
import asyncio

from qmtl.gateway.api import create_app, Database
from qmtl.common import crc32_of_list
from qmtl.gateway.dagmanager_client import DagManagerClient
from qmtl.dagmanager.grpc_server import serve
from qmtl.dagmanager.diff_service import StreamSender, Neo4jNodeRepository
import grpc
from qmtl.dagmanager.monitor import AckStatus


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

    def wait_for_ack(self) -> AckStatus:
        return AckStatus.OK

    def ack(self, status: AckStatus = AckStatus.OK):
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

    async def get_queues_by_tag(self, tags, interval, match_mode="any"):
        self.called_with = (tags, interval, match_mode)
        return [{"queue": "q1", "global": False}, {"queue": "q2", "global": False}]


@pytest.fixture
def client(fake_redis):
    dag = DummyDag()
    app = create_app(redis_client=fake_redis, database=FakeDB(), dag_client=dag, enable_background=False)
    with TestClient(app) as c:
        yield c, dag
    asyncio.run(dag.close())


def test_queues_by_tag_route(client):
    c, dag = client
    resp = c.get(
        "/queues/by_tag",
        params={"tags": "t1,t2", "interval": "60", "match_mode": "any"},
    )
    assert resp.status_code == 200
    assert resp.json()["queues"] == [
        {"queue": "q1", "global": False},
        {"queue": "q2", "global": False},
    ]
    assert dag.called_with == (["t1", "t2"], 60, "any")


def test_queues_by_tag_route_all_mode(client):
    c, dag = client
    resp = c.get(
        "/queues/by_tag",
        params={"tags": "t1,t2", "interval": "60", "match_mode": "all"},
    )
    assert resp.status_code == 200
    assert resp.json()["queues"] == [
        {"queue": "q1", "global": False},
        {"queue": "q2", "global": False},
    ]
    assert dag.called_with == (["t1", "t2"], 60, "all")


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
        "node_ids_crc32": crc32_of_list(["N1"]),
    }
    resp = c.post("/strategies", json=payload)
    assert resp.status_code == 202
    assert resp.json()["queue_map"] == {
        "N1": [
            {"queue": "q1", "global": False},
            {"queue": "q2", "global": False},
        ]
    }
    assert dag.called_with == (["t1"], 60, "any")


def test_multiple_tag_query_nodes_handle_errors(fake_redis):
    class ErrorDag(DagManagerClient):
        def __init__(self):
            super().__init__("dummy")
            self.calls = []

        async def get_queues_by_tag(self, tags, interval, match_mode="any"):
            self.calls.append((tags, interval, match_mode))
            if "bad" in tags:
                raise RuntimeError("boom")
            return [{"queue": f"{tags[0]}_q", "global": False}]

    dag = ErrorDag()
    app = create_app(redis_client=fake_redis, database=FakeDB(), dag_client=dag, enable_background=False)
    with TestClient(app) as c:
        dag_json = {
            "nodes": [
                {
                    "node_id": "N1",
                    "node_type": "TagQueryNode",
                    "interval": 60,
                    "period": 2,
                    "tags": ["good"],
                    "code_hash": "ch",
                    "schema_hash": "sh",
                    "inputs": [],
                },
                {
                    "node_id": "N2",
                    "node_type": "TagQueryNode",
                    "interval": 30,
                    "period": 2,
                    "tags": ["bad"],
                    "code_hash": "ch",
                    "schema_hash": "sh",
                    "inputs": [],
                },
            ]
        }
        payload = {
            "dag_json": base64.b64encode(json.dumps(dag_json).encode()).decode(),
            "meta": None,
            "node_ids_crc32": crc32_of_list(["N1", "N2"]),
        }
        resp = c.post("/strategies", json=payload)
        assert resp.status_code == 202
        assert resp.json()["queue_map"] == {
            "N1": [{"queue": "good_q", "global": False}],
            "N2": [],
        }
        assert len(dag.calls) == 2
    asyncio.run(dag.close())


@pytest.mark.asyncio
@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
async def test_dag_client_queries_grpc():
    driver = _FakeDriver([{"topic": "q1"}, {"topic": "q2"}])
    admin = _FakeAdmin()
    stream = _FakeStream()
    server, port = serve(driver, admin, stream, host="127.0.0.1", port=0)
    await server.start()
    client = DagManagerClient(f"127.0.0.1:{port}")
    try:
        queues = await client.get_queues_by_tag(["t"], 60, "any")
        assert queues == [
            {"queue": "q1", "global": False},
            {"queue": "q2", "global": False},
        ]
    finally:
        await client.close()
        await server.stop(None)
        await server.wait_for_termination()
        client = None
        server = None
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            gc.collect()


def test_repository_match_modes():
    class CaptureDriver:
        def __init__(self):
            self.last_query = ""

        class Session:
            def __init__(self, driver: 'CaptureDriver') -> None:
                self.driver = driver

            def run(self, query, **params):
                self.driver.last_query = query
                return []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                pass

        def session(self):
            return CaptureDriver.Session(self)

    driver = CaptureDriver()
    repo = Neo4jNodeRepository(driver)
    repo.get_queues_by_tag(["a"], 60, "any")
    assert "any(" in driver.last_query.lower()
    repo.get_queues_by_tag(["a"], 60, "all")
    assert "all(" in driver.last_query.lower()
