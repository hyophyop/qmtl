import asyncio

import pytest

from types import SimpleNamespace

from qmtl.gateway.queue import RedisFIFOQueue
from qmtl.gateway.worker import StrategyWorker
from qmtl.gateway.database import Database
from qmtl.gateway.fsm import StrategyFSM
from qmtl.gateway.ws import WebSocketHub


class FakeDB(Database):
    def __init__(self) -> None:
        self.records: dict[str, str] = {}
        self.completions: list[str] = []
        self.events: list[tuple[str, str]] = []

    async def insert_strategy(self, strategy_id: str, meta=None) -> None:  # pragma: no cover - not used
        self.records[strategy_id] = "queued"

    async def set_status(self, strategy_id: str, status: str) -> None:
        self.records[strategy_id] = status
        if status == "completed":
            self.completions.append(strategy_id)

    async def get_status(self, strategy_id: str) -> str | None:
        return self.records.get(strategy_id)

    async def append_event(self, strategy_id: str, event: str) -> None:  # pragma: no cover - not used
        self.events.append((strategy_id, event))


@pytest.mark.asyncio
async def test_worker_locking_single_processing(fake_redis):
    redis = fake_redis
    queue = RedisFIFOQueue(redis, "strategy_queue")
    db = FakeDB()
    fsm = StrategyFSM(redis, db)

    await fsm.create("sid", None)
    await redis.hset("strategy:sid", mapping={"dag": "{}"})

    await queue.push("sid")
    await queue.push("sid")

    async def diff(sid: str, dag: str):
        return SimpleNamespace(queue_map={}, sentinel_id="s")

    dag_client = SimpleNamespace(diff=diff)

    w1 = StrategyWorker(redis, db, fsm, queue, dag_client, ws_hub=None)
    w2 = StrategyWorker(redis, db, fsm, queue, dag_client, ws_hub=None)

    await asyncio.gather(w1.run_once(), w2.run_once())
    await asyncio.gather(w1.run_once(), w2.run_once())

    assert db.completions.count("sid") == 1
    assert db.records["sid"] == "completed"


class DummyHub(WebSocketHub):
    def __init__(self) -> None:
        super().__init__()
        self.progress: list[tuple[str, str]] = []
        self.maps: list[tuple[str, dict]] = []

    async def send_progress(self, strategy_id: str, status: str) -> None:  # type: ignore[override]
        self.progress.append((strategy_id, status))

    async def send_queue_map(self, strategy_id: str, queue_map: dict[str, list[str] | str]) -> None:  # type: ignore[override]
        self.maps.append((strategy_id, queue_map))


@pytest.mark.asyncio
async def test_worker_diff_success_broadcasts(fake_redis):
    redis = fake_redis
    queue = RedisFIFOQueue(redis, "strategy_queue")
    db = FakeDB()
    fsm = StrategyFSM(redis, db)

    await fsm.create("sid", None)
    await redis.hset("strategy:sid", mapping={"dag": "{}"})
    await queue.push("sid")

    called = []

    async def diff(sid: str, dag: str):
        called.append((sid, dag))
        return SimpleNamespace(queue_map={"n": "t"}, sentinel_id="s")

    dag_client = SimpleNamespace(diff=diff)
    hub = DummyHub()
    worker = StrategyWorker(redis, db, fsm, queue, dag_client, hub)
    await worker.run_once()

    assert called == [("sid", "{}")]
    assert hub.maps == [("sid", {"n": "t"})]
    assert hub.progress[0] == ("sid", "processing")
    assert hub.progress[-1] == ("sid", "completed")
    assert db.records["sid"] == "completed"


@pytest.mark.asyncio
async def test_worker_diff_failure_sets_failed_and_broadcasts(fake_redis):
    redis = fake_redis
    queue = RedisFIFOQueue(redis, "strategy_queue")
    db = FakeDB()
    fsm = StrategyFSM(redis, db)

    await fsm.create("sid", None)
    await redis.hset("strategy:sid", mapping={"dag": "{}"})
    await queue.push("sid")

    called = []

    async def diff(sid: str, dag: str):
        called.append((sid, dag))
        raise RuntimeError("fail")

    dag_client = SimpleNamespace(diff=diff)
    hub = DummyHub()
    worker = StrategyWorker(redis, db, fsm, queue, dag_client, hub)
    await worker.run_once()

    assert called == [("sid", "{}")]
    assert hub.maps == []
    assert hub.progress[0] == ("sid", "processing")
    assert hub.progress[-1] == ("sid", "failed")
    assert db.records["sid"] == "failed"

