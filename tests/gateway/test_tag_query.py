import json
import base64
import gc
import pytest
from fastapi.testclient import TestClient
import asyncio

from qmtl.gateway.api import create_app, Database
from qmtl.gateway.dagmanager_client import DagManagerClient
from qmtl.dagmanager.grpc_server import serve
from qmtl.dagmanager.diff_service import StreamSender, Neo4jNodeRepository
import grpc
from qmtl.dagmanager.monitor import AckStatus
from tests.factories import node_ids_crc32, tag_query_node_payload


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

    async def get_queues_by_tag(
        self, tags, interval, match_mode="any", world_id=None, execution_domain=None
    ):
        self.called_with = (tags, interval, match_mode, world_id, execution_domain)
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
    assert dag.called_with == (["t1", "t2"], 60, "any", None, None)


def test_queues_by_tag_route_default_match_mode(client):
    c, dag = client
    resp = c.get(
        "/queues/by_tag",
        params={"tags": "t1,t2", "interval": "60"},
    )
    assert resp.status_code == 200
    assert resp.json()["queues"] == [
        {"queue": "q1", "global": False},
        {"queue": "q2", "global": False},
    ]
    assert dag.called_with == (["t1", "t2"], 60, "any", None, None)


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
    assert dag.called_with == (["t1", "t2"], 60, "all", None, None)


def test_submit_tag_query_node(client):
    c, dag = client
    node = tag_query_node_payload(
        tags=["t1"],
        interval=60,
        period=2,
        code_hash="ch",
        config_hash="cfg",
        schema_hash="sh",
        schema_compat_id="sh-major",
        inputs=[],
    )
    dag_json = {"nodes": [node]}
    payload = {
        "dag_json": base64.b64encode(json.dumps(dag_json).encode()).decode(),
        "meta": None,
        "node_ids_crc32": node_ids_crc32([node]),
    }
    resp = c.post("/strategies", json=payload)
    assert resp.status_code == 202
    assert resp.json()["queue_map"] == {
        _TAGQUERY_ID: [
            {"queue": "q1", "global": False},
            {"queue": "q2", "global": False},
        ]
    }
    assert dag.called_with == (["t1"], 60, "any", None, None)


def test_multiple_tag_query_nodes_handle_errors(fake_redis):
    class ErrorDag(DagManagerClient):
        def __init__(self):
            super().__init__("dummy")
            self.calls = []

        async def get_queues_by_tag(
            self, tags, interval, match_mode="any", world_id=None, execution_domain=None
        ):
            self.calls.append((tags, interval, match_mode, world_id, execution_domain))
            if "bad" in tags:
                raise RuntimeError("boom")
            return [{"queue": f"{tags[0]}_q", "global": False}]

    dag = ErrorDag()
    app = create_app(redis_client=fake_redis, database=FakeDB(), dag_client=dag, enable_background=False)
    with TestClient(app) as c:
            good_node = tag_query_node_payload(
                tags=["good"],
                interval=60,
                period=2,
                code_hash="ch",
                config_hash="cfg",
                schema_hash="sh",
                schema_compat_id="sh-major",
                inputs=[],
            )
            bad_node = tag_query_node_payload(
                tags=["bad"],
                interval=30,
                period=2,
                code_hash="ch",
                config_hash="cfg2",
                schema_hash="sh",
                schema_compat_id="sh-major",
                inputs=[],
            )
            good_node_id = good_node["node_id"]
            bad_node_id = bad_node["node_id"]
            dag_json = {"nodes": [good_node, bad_node]}
            payload = {
                "dag_json": base64.b64encode(json.dumps(dag_json).encode()).decode(),
                "meta": None,
                "node_ids_crc32": node_ids_crc32([good_node, bad_node]),
            }
            resp = c.post("/strategies", json=payload)
            assert resp.status_code == 202
            assert resp.json()["queue_map"] == {
                good_node_id: [{"queue": "good_q", "global": False}],
                bad_node_id: [],
            }
            assert len(dag.calls) == 2
    asyncio.run(dag.close())


@pytest.mark.asyncio
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
_TAGQUERY_NODE = tag_query_node_payload(
    tags=["t1"],
    interval=60,
    period=2,
    code_hash="ch",
    config_hash="cfg",
    schema_hash="sh",
    schema_compat_id="sh-major",
)
_TAGQUERY_ID = _TAGQUERY_NODE["node_id"]
_TAGQUERY_ALT_NODE = tag_query_node_payload(
    tags=["bad"],
    interval=30,
    period=2,
    code_hash="ch",
    config_hash="cfg",
    schema_hash="sh",
    schema_compat_id="sh-major",
)
_TAGQUERY_ALT_ID = _TAGQUERY_ALT_NODE["node_id"]
