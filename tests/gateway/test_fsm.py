import pytest

from qmtl.gateway.fsm import StrategyFSM
from qmtl.gateway.database import Database


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
async def test_state_recovery_after_redis_failure(fake_redis):
    redis = fake_redis
    db = FakeDB()
    fsm = StrategyFSM(redis, db)

    await fsm.create("s1", None)
    await fsm.transition("s1", "PROCESS")
    assert await fsm.get("s1") == "processing"
    assert db.events[-1] == ("s1", "PROCESS")

    events_before = list(db.events)

    await redis.flushall()

    recovered = await fsm.get("s1")
    assert recovered == "processing"
    assert await redis.hget("strategy:s1", "state") == "processing"

    assert db.events == events_before

    await fsm.transition("s1", "COMPLETE")
    assert db.events[-1] == ("s1", "COMPLETE")
    assert await fsm.get("s1") == "completed"
