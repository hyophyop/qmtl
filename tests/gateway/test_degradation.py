import pytest
from fastapi.testclient import TestClient

from qmtl.gateway.api import create_app, StrategySubmit
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
    await mgr.start()
    await mgr.trigger()
    assert mgr.level == DegradationLevel.NORMAL

    dag.ok = False
    await mgr.trigger()
    assert mgr.level == DegradationLevel.PARTIAL

    db.ok = False
    await mgr.trigger()
    assert mgr.level == DegradationLevel.MINIMAL

    redis.ok = False
    monkeypatch.setattr("psutil.cpu_percent", lambda interval=None: 96)
    await mgr.trigger()
    assert mgr.level == DegradationLevel.STATIC
    await mgr.stop()


def make_app(fake_redis):
    db = FakeDB()
    app = create_app(redis_client=fake_redis, database=db, dag_client=DummyDag())
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
        run_type="dry-run",
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
