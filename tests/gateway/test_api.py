import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from fakeredis.aioredis import FakeRedis

from qmtl.gateway.api import create_app, Database, StrategySubmit


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
def app():
    redis = FakeRedis(decode_responses=True)
    db = FakeDB()
    return create_app(redis_client=redis, database=db)


def test_ingest_and_status(app):
    client = TestClient(app)
    payload = StrategySubmit(dag_json="{}", meta={"user": "alice"}, run_type="dry-run")
    resp = client.post("/strategies", json=payload.model_dump())
    assert resp.status_code == 202
    sid = resp.json()["strategy_id"]

    resp = client.get(f"/strategies/{sid}/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"
