import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from qmtl.gateway.api import create_app, Database, StrategySubmit
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
    return create_app(redis_client=fake_redis, database=db)


def test_ingest_and_status(app):
    with TestClient(app) as client:
        payload = StrategySubmit(
            dag_json="{}",
            meta={"user": "alice"},
            run_type="dry-run",
            node_ids_crc32=crc32_of_list([]),
        )
        resp = client.post("/strategies", json=payload.model_dump())
        assert resp.status_code == 202
        sid = resp.json()["strategy_id"]

        resp = client.get(f"/strategies/{sid}/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"
