import asyncio

import pytest
from fakeredis.aioredis import FakeRedis

from qmtl.gateway.queue import RedisFIFOQueue
from qmtl.gateway.worker import StrategyWorker
from qmtl.gateway.api import Database
from qmtl.gateway.fsm import StrategyFSM


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
async def test_worker_locking_single_processing():
    redis = FakeRedis(decode_responses=True)
    queue = RedisFIFOQueue(redis, "strategy_queue")
    db = FakeDB()
    fsm = StrategyFSM(redis, db)

    await fsm.create("sid", None)

    await queue.push("sid")
    await queue.push("sid")

    w1 = StrategyWorker(redis, db, fsm, queue)
    w2 = StrategyWorker(redis, db, fsm, queue)

    await asyncio.gather(w1.run_once(), w2.run_once())
    await asyncio.gather(w1.run_once(), w2.run_once())

    assert db.completions.count("sid") == 1
    assert db.records["sid"] == "completed"

