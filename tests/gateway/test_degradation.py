import asyncio
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from qmtl.gateway.api import create_app
from qmtl.gateway.models import StrategySubmit
from qmtl.gateway.database import Database
from qmtl.gateway.degradation import DegradationManager, DegradationLevel
from qmtl.common import crc32_of_list


class FakeDB(Database):
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok

    async def insert_strategy(self, strategy_id: str, meta=None) -> None:  # pragma: no cover - not used
        pass

    async def set_status(self, strategy_id: str, status: str) -> None:  # pragma: no cover - not used
        pass

    async def get_status(self, strategy_id: str):  # pragma: no cover - not used
        return "queued"

    async def append_event(self, strategy_id: str, event: str) -> None:  # pragma: no cover - not used
        pass

    async def healthy(self) -> bool:
        return self.ok


class DummyDag:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok

    async def status(self) -> bool:
        return self.ok


class DummyRedis:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok

    async def ping(self) -> bool:
        if not self.ok:
            raise RuntimeError("fail")
        return True

    async def rpush(self, *a, **k):
        pass

    async def hset(self, *a, **k):
        pass

    async def set(self, *a, **k):
        pass


@pytest.mark.asyncio
async def test_level_transitions(monkeypatch):
    redis = DummyRedis()
    db = FakeDB()
    dag = DummyDag()
    mgr = DegradationManager(redis, db, dag, check_interval=0.01)
    monkeypatch.setattr("psutil.cpu_percent", lambda interval=None: 10)
    await mgr.update()
    assert mgr.level == DegradationLevel.NORMAL

    dag.ok = False
    await mgr.update()
    assert mgr.level == DegradationLevel.PARTIAL

    db.ok = False
    await mgr.update()
    assert mgr.level == DegradationLevel.MINIMAL

    redis.ok = False
    monkeypatch.setattr("psutil.cpu_percent", lambda interval=None: 96)
    await mgr.update()
    assert mgr.level == DegradationLevel.STATIC


@pytest.mark.asyncio
async def test_check_dependencies_parallel(monkeypatch):
    redis = DummyRedis()
    db = FakeDB()
    dag = DummyDag()
    mgr = DegradationManager(redis, db, dag)
    monkeypatch.setattr("psutil.cpu_percent", lambda interval=None: 0)

    start_times: dict[str, float] = {}

    done: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    async def record(name: str) -> bool:
        start_times[name] = asyncio.get_running_loop().time()
        await done
        return True

    async def record_redis() -> bool:
        return await record("redis")

    async def record_db() -> bool:
        return await record("db")

    async def record_dag() -> bool:
        return await record("dag")

    redis.ping = AsyncMock(side_effect=record_redis)
    db.healthy = AsyncMock(side_effect=record_db)
    dag.status = AsyncMock(side_effect=record_dag)

    start = asyncio.get_running_loop().time()
    eval_task = asyncio.create_task(mgr.evaluate())
    try:
        await asyncio.wait_for(asyncio.shield(eval_task), timeout=0.01)
    except asyncio.TimeoutError:
        pass
    done.set_result(None)
    await eval_task
    duration = asyncio.get_running_loop().time() - start

    assert duration < 0.25
    assert max(start_times.values()) - min(start_times.values()) < 0.05
    redis.ping.assert_awaited_once()
    db.healthy.assert_awaited_once()
    dag.status.assert_awaited_once()


@pytest.mark.asyncio
async def test_flushes_local_queue(monkeypatch):
    redis = DummyRedis()
    redis.rpush = AsyncMock()
    db = FakeDB()
    dag = DummyDag(ok=False)
    mgr = DegradationManager(redis, db, dag)
    monkeypatch.setattr("psutil.cpu_percent", lambda interval=None: 0)

    await mgr.update()
    assert mgr.level == DegradationLevel.PARTIAL

    mgr.local_queue.append("s1")
    dag.ok = True
    await mgr.update()

    redis.rpush.assert_awaited_once_with("strategy_queue", "s1")
    assert mgr.local_queue == []
    assert mgr.level == DegradationLevel.NORMAL


def make_app(fake_redis):
    db = FakeDB()
    app = create_app(
        redis_client=fake_redis,
        database=db,
        dag_client=DummyDag(),
        enable_background=False,
    )
    async def nop():
        return None

    app.state.degradation.start = nop
    app.state.degradation.stop = nop
    return app

def test_status_includes_level(fake_redis):
    app = make_app(fake_redis)
    with TestClient(app) as client:
        resp = client.get("/status")
        assert resp.status_code == 200
        assert resp.json()["degrade_level"] == "NORMAL"

def test_minimal_blocks_submission(fake_redis):
    app = make_app(fake_redis)
    app.state.degradation.level = DegradationLevel.MINIMAL
    payload = StrategySubmit(
        dag_json="{}",
        meta=None,
        node_ids_crc32=crc32_of_list([]),
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post("/strategies", json=payload.model_dump())
        assert resp.status_code == 503

def test_static_returns_204(fake_redis):
    app = make_app(fake_redis)
    app.state.degradation.level = DegradationLevel.STATIC
    with TestClient(app) as client:
        resp = client.get("/status")
        assert resp.status_code == 204
        assert resp.headers.get("Retry-After") == "30"
