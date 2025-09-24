import pytest
import redis.asyncio as redis

from qmtl.services.gateway.fsm import StrategyFSM, FSMError, TransitionError
from qmtl.services.gateway.database import Database


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


@pytest.mark.asyncio
async def test_create_logs_and_raises_on_redis_error(monkeypatch, fake_redis, caplog):
    redis_client = fake_redis
    db = FakeDB()
    fsm = StrategyFSM(redis_client, db)

    async def boom(*args, **kwargs):
        raise redis.RedisError("boom")

    monkeypatch.setattr(redis_client, "hset", boom)
    caplog.set_level("ERROR")
    with pytest.raises(FSMError):
        await fsm.create("s1", None)
    assert "Redis error creating strategy" in caplog.text


@pytest.mark.asyncio
async def test_transition_logs_and_raises_on_redis_error(monkeypatch, fake_redis, caplog):
    redis_client = fake_redis
    db = FakeDB()
    fsm = StrategyFSM(redis_client, db)
    await fsm.create("s1", None)

    async def boom(*args, **kwargs):
        raise redis.RedisError("boom")

    monkeypatch.setattr(redis_client, "hset", boom)
    caplog.set_level("ERROR")
    with pytest.raises(TransitionError):
        await fsm.transition("s1", "PROCESS")
    assert "Redis error during transition" in caplog.text


@pytest.mark.asyncio
async def test_get_recovers_on_redis_error(monkeypatch, fake_redis, caplog):
    redis_client = fake_redis
    db = FakeDB()
    fsm = StrategyFSM(redis_client, db)
    await fsm.create("s1", None)
    await fsm.transition("s1", "PROCESS")

    original_hget = redis_client.hget

    async def fail_once(*args, **kwargs):
        if not getattr(fail_once, "called", False):
            fail_once.called = True
            raise redis.RedisError("boom")
        return await original_hget(*args, **kwargs)

    monkeypatch.setattr(redis_client, "hget", fail_once)
    caplog.set_level("ERROR")

    state = await fsm.get("s1")
    assert state == "processing"
    assert await redis_client.hget("strategy:s1", "state") == "processing"
    assert "Redis error retrieving strategy" in caplog.text
