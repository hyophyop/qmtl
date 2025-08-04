from datetime import datetime, UTC
from fastapi.testclient import TestClient

from qmtl.gateway.api import create_app as gw_create_app
from qmtl.dagmanager.http_server import create_app as dag_http_create_app
from qmtl.dagmanager.api import create_app as dag_api_create_app
from qmtl.dagmanager.gc import QueueInfo
from qmtl.gateway.redis_queue import RedisTaskQueue
from qmtl.gateway.dagmanager_client import DagManagerClient
from qmtl.gateway.ws import WebSocketHub
from qmtl.gateway.worker import StrategyWorker
from qmtl.gateway.fsm import StrategyFSM
from qmtl.gateway.database import PostgresDatabase

import grpc
import asyncio
import gc
import pytest


class DummyGC:
    def collect(self):
        return [QueueInfo("q", "raw", datetime.now(UTC), interval="60s")]


class FakeDagClient:
    async def status(self):
        return True

    async def close(self) -> None:
        pass


class FakeDB(PostgresDatabase):
    def __init__(self):
        super().__init__("postgresql://localhost/test")
        self._pool = None

    async def healthy(self):
        return True


def test_gateway_health(fake_redis):
    redis_client = fake_redis
    db = FakeDB()
    with TestClient(
        gw_create_app(redis_client=redis_client, database=db, dag_client=FakeDagClient())
    ) as client:
        resp = client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["redis"] == "ok"
        assert data["postgres"] == "ok"
        assert data["dag_manager"] == "ok"


def test_dagmanager_http_health():
    with TestClient(dag_http_create_app()) as client:
        resp = client.get("/status")
        assert resp.status_code == 200
        assert resp.json()["neo4j"] in {"ok", "error", "unknown"}


def test_dagmanager_api_health():
    with TestClient(dag_api_create_app(DummyGC())) as client:
        resp = client.get("/status")
        assert resp.status_code == 200
        assert "neo4j" in resp.json()


@pytest.mark.asyncio
async def test_grpc_health():
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
    client = DagManagerClient(f"127.0.0.1:{port}")
    try:
        assert await client.status() is True
    finally:
        await client.close()
        await server.stop(None)
        await server.wait_for_termination()
        gc.collect()


@pytest.mark.asyncio
async def test_queue_healthy(fake_redis):
    redis = fake_redis
    queue = RedisTaskQueue(redis)
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
    queue = RedisTaskQueue(redis)
    client = DagManagerClient("127.0.0.1:1")
    async def status():
        return True
    monkeypatch.setattr(client, "status", status)

    worker = StrategyWorker(redis, db, fsm, queue, client)
    assert await worker.healthy() is True
    await client.close()
