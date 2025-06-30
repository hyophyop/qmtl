from datetime import datetime, UTC
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
from qmtl.gateway.database import PostgresDatabase

import grpc
import asyncio
import pytest


class DummyGC:
    def collect(self):
        return [QueueInfo("q", "raw", datetime.now(UTC), interval=60)]


class FakeDagClient:
    async def status(self):
        return True


class FakeDB(PostgresDatabase):
    def __init__(self):
        super().__init__("postgresql://localhost/test")
        self._pool = None

    async def healthy(self):
        return True


def test_gateway_status(fake_redis):
    redis_client = fake_redis
    db = FakeDB()
    client = TestClient(
        gw_create_app(redis_client=redis_client, database=db, dag_client=FakeDagClient())
    )
    resp = client.get("/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["redis"] == "ok"
    assert data["postgres"] == "ok"
    assert data["dag_manager"] == "ok"


def test_dagmanager_http_status():
    client = TestClient(dag_http_create_app())
    resp = client.get("/status")
    assert resp.status_code == 200
    assert resp.json()["neo4j"] in {"ok", "error", "unknown"}


def test_dagmanager_api_status():
    client = TestClient(dag_api_create_app(DummyGC()))
    resp = client.get("/status")
    assert resp.status_code == 200
    assert "neo4j" in resp.json()


@pytest.mark.asyncio
async def test_grpc_status():
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
        assert await client.status() is True
    finally:
        await server.stop(None)


@pytest.mark.asyncio
async def test_queue_healthy(fake_redis):
    redis = fake_redis
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
async def test_worker_healthy(monkeypatch, fake_redis):
    redis = fake_redis

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
    async def status():
        return True
    monkeypatch.setattr(client, "status", status)

    worker = StrategyWorker(redis, db, fsm, queue, client)
    assert await worker.healthy() is True
