import asyncio
import pytest
from fakeredis.aioredis import FakeRedis

from qmtl.gateway.worker import StrategyWorker
from qmtl.gateway.queue import RedisFIFOQueue
from qmtl.gateway.fsm import StrategyFSM
from qmtl.gateway.api import Database


class FakeDB(Database):
    def __init__(self) -> None:
        self.states: dict[str, str] = {}

    async def insert_strategy(self, strategy_id: str, meta=None) -> None:
        self.states[strategy_id] = "queued"

    async def set_status(self, strategy_id: str, status: str) -> None:
        self.states[strategy_id] = status

    async def get_status(self, strategy_id: str):
        return self.states.get(strategy_id)

    async def append_event(self, strategy_id: str, event: str) -> None:
        pass


class DummyDag:
    async def diff(self, sid: str, dag: str):
        raise RuntimeError("grpc fail")


class DummyAlerts:
    def __init__(self):
        self.slack: list[str] = []

    async def send_slack(self, msg: str) -> None:
        self.slack.append(msg)

    async def send_pagerduty(self, msg: str) -> None:
        self.slack.append(msg)


@pytest.mark.asyncio
async def test_worker_alerts_after_repeated_failures():
    redis = FakeRedis(decode_responses=True)
    queue = RedisFIFOQueue(redis, "strategy_queue")
    db = FakeDB()
    fsm = StrategyFSM(redis, db)
    alerts = DummyAlerts()
    worker = StrategyWorker(
        redis,
        db,
        fsm,
        queue,
        DummyDag(),
        ws_hub=None,
        alert_manager=alerts,
        grpc_fail_threshold=2,
    )

    # enqueue three strategies that will all fail
    for sid in ["s1", "s2", "s3"]:
        await fsm.create(sid, None)
        await redis.hset(f"strategy:{sid}", mapping={"dag": "{}"})
        await queue.push(sid)

    for _ in range(3):
        await worker.run_once()

    assert len(alerts.slack) == 1
