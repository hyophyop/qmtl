import pytest

from qmtl.gateway.redis_client import InMemoryRedis
from qmtl.gateway.redis_queue import RedisTaskQueue
from qmtl.gateway.fsm import StrategyFSM
from qmtl.gateway.api import Database


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

    assert await queue.pop() == "a"
    assert await queue.pop() == "b"
    assert await queue.pop() is None


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
