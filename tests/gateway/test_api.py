import pytest
import httpx

from qmtl.gateway.api import create_app, Database
from qmtl.gateway.models import StrategySubmit
from qmtl.common import crc32_of_list


class FakeDB(Database):
    def __init__(self):
        self.records = {}
        self.events = []

    async def insert_strategy(self, strategy_id: str, meta: dict | None) -> None:
        self.records[strategy_id] = {"meta": meta, "status": "queued"}

    async def set_status(self, strategy_id: str, status: str) -> None:
        if strategy_id in self.records:
            self.records[strategy_id]["status"] = status

    async def get_status(self, strategy_id: str) -> str | None:
        rec = self.records.get(strategy_id)
        return rec.get("status") if rec else None

    async def append_event(self, strategy_id: str, event: str) -> None:  # pragma: no cover - not used
        self.events.append((strategy_id, event))


@pytest.fixture
def app(fake_redis):
    db = FakeDB()
    return create_app(redis_client=fake_redis, database=db, enable_background=False)


@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
@pytest.mark.asyncio
async def test_ingest_and_status(app):
    transport = httpx.ASGITransport(app=app, lifespan="on")
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        payload = StrategySubmit(
            dag_json="{}",
            meta={"user": "alice"},
            node_ids_crc32=crc32_of_list([]),
        )
        resp = await client.post("/strategies", json=payload.model_dump())
        assert resp.status_code == 202
        sid = resp.json()["strategy_id"]

        resp = await client.get(f"/strategies/{sid}/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"
    await transport.aclose()
