from datetime import datetime
from fastapi.testclient import TestClient

from qmtl.gateway.api import create_app as gw_create_app
from qmtl.dagmanager.http_server import create_app as dag_http_create_app
from qmtl.dagmanager.api import create_app as dag_api_create_app
from qmtl.dagmanager.gc import QueueInfo
from qmtl.gateway.queue import RedisFIFOQueue
from qmtl.gateway.dagmanager_client import DagManagerClient
from qmtl.gateway.ws import WebSocketHub
from qmtl.gateway.worker import StrategyWorker
from qmtl.gateway.fsm import StrategyFSM
from qmtl.gateway.api import PostgresDatabase

import fakeredis
import grpc
import asyncio
import pytest


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


@pytest.mark.asyncio
async def test_grpc_ping():
    from qmtl.dagmanager.grpc_server import serve

    class FakeDriver:
        def session(self):
            class S:
                def run(self, *a, **k):
                    return []

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    pass

            return S()

    class FakeAdmin:
        def list_topics(self):
            return {}

        def create_topic(self, *a, **k):
            pass

    class FakeStream:
        def send(self, chunk):
            pass

        def wait_for_ack(self):
            pass

        def ack(self):
            pass

    driver = FakeDriver()
    admin = FakeAdmin()
    stream = FakeStream()
    server, port = serve(driver, admin, stream, host="127.0.0.1", port=0)
    await server.start()
    try:
        client = DagManagerClient(f"127.0.0.1:{port}")
        assert await client.ping() is True
    finally:
        await server.stop(None)


@pytest.mark.asyncio
async def test_queue_healthy():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    queue = RedisFIFOQueue(redis)
    assert await queue.healthy() is True


@pytest.mark.asyncio
async def test_ws_hub_is_running():
    hub = WebSocketHub()
    assert hub.is_running() is False
    await hub.start()
    try:
        assert hub.is_running() is True
    finally:
        await hub.stop()


@pytest.mark.asyncio
async def test_worker_healthy(monkeypatch):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    class FakeDB(PostgresDatabase):
        def __init__(self):
            super().__init__("postgresql://localhost/test")
            self._pool = None

        async def healthy(self):
            return True

    db = FakeDB()
    fsm = StrategyFSM(redis, db)
    queue = RedisFIFOQueue(redis)
    client = DagManagerClient("127.0.0.1:1")
    async def ping():
        return True
    monkeypatch.setattr(client, "ping", ping)

    worker = StrategyWorker(redis, db, fsm, queue, client)
    assert await worker.healthy() is True
