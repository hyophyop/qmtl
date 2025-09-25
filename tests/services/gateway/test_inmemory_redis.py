import pytest

from qmtl.services.gateway.redis_client import InMemoryRedis
from qmtl.services.gateway.redis_queue import RedisTaskQueue
from qmtl.services.gateway.fsm import StrategyFSM
from qmtl.services.gateway.api import Database


class FakeDB(Database):
    def __init__(self) -> None:
        self.states: dict[str, str] = {}
        self.events: list[tuple[str, str]] = []

    async def insert_strategy(self, strategy_id: str, meta=None) -> None:
        self.states[strategy_id] = "queued"

    async def set_status(self, strategy_id: str, status: str) -> None:
        self.states[strategy_id] = status

    async def get_status(self, strategy_id: str) -> str | None:
        return self.states.get(strategy_id)

    async def append_event(self, strategy_id: str, event: str) -> None:
        self.events.append((strategy_id, event))


@pytest.mark.asyncio
async def test_queue_push_pop_order():
    redis = InMemoryRedis()
    queue = RedisTaskQueue(redis, "q")

    await queue.push("a")
    await queue.push("b")

    worker = "worker-1"

    item = await queue.pop(worker)
    assert item == "a"
    await queue.release(item, worker)

    item = await queue.pop(worker)
    assert item == "b"
    await queue.release(item, worker)

    assert await queue.pop(worker) is None


@pytest.mark.asyncio
async def test_fsm_state_recovery():
    redis = InMemoryRedis()
    db = FakeDB()
    fsm = StrategyFSM(redis, db)

    await fsm.create("sid", None)
    await fsm.transition("sid", "PROCESS")

    await redis.flushall()

    recovered = await fsm.get("sid")
    assert recovered == "processing"
    assert await redis.hget("strategy:sid", "state") == "processing"
