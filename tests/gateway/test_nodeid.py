import base64
import json
import hashlib
import pytest
from fastapi.testclient import TestClient

from qmtl.common import compute_node_id, crc32_of_list
from qmtl.gateway.api import create_app, Database
from qmtl.gateway.models import StrategySubmit

# Ignore unraisable exception warnings produced by event loop cleanup in TestClient
pytestmark = pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")


class FakeDB(Database):
    def __init__(self) -> None:
        self.records = {}
        self.events = []

    async def insert_strategy(self, strategy_id: str, meta=None) -> None:  # pragma: no cover - not used
        self.records[strategy_id] = {"status": "queued", "meta": meta}

    async def set_status(self, strategy_id: str, status: str) -> None:  # pragma: no cover - not used
        self.records[strategy_id]["status"] = status

    async def get_status(self, strategy_id: str) -> str | None:  # pragma: no cover - not used
        rec = self.records.get(strategy_id)
        return rec.get("status") if rec else None

    async def append_event(self, strategy_id: str, event: str) -> None:  # pragma: no cover - not used
        self.events.append((strategy_id, event))


@pytest.fixture
def client_and_redis(fake_redis):
    db = FakeDB()
    app = create_app(redis_client=fake_redis, database=db, enable_background=False)
    with TestClient(app) as c:
        yield c, fake_redis


def test_compute_node_id_collision():
    data = ("A", "B", "C", "D")
    first = compute_node_id(*data)
    second = compute_node_id(*data, existing_ids={first})
    assert first != second
    assert second == hashlib.sha3_256(b"A:B:C:D").hexdigest()


@pytest.mark.asyncio
async def test_node_id_mismatch(client_and_redis):
    client, _ = client_and_redis
    node = {
        "node_type": "N",
        "code_hash": "c",
        "config_hash": "cfg",
        "schema_hash": "s",
        "node_id": "wrong",
    }
    dag = {"nodes": [node]}
    payload = StrategySubmit(
        dag_json=base64.b64encode(json.dumps(dag).encode()).decode(),
        meta=None,
        node_ids_crc32=crc32_of_list(["wrong"]),
    )
    resp = client.post("/strategies", json=payload.model_dump())
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "node_id_mismatch" in detail


@pytest.mark.asyncio
async def test_sentinel_inserted(client_and_redis):
    client, redis = client_and_redis
    dag = {"nodes": []}
    payload = StrategySubmit(
        dag_json=base64.b64encode(json.dumps(dag).encode()).decode(),
        meta=None,
        node_ids_crc32=crc32_of_list([]),
    )
    resp = client.post("/strategies", json=payload.model_dump())
    assert resp.status_code == 202
    sid = resp.json()["strategy_id"]
    encoded = await redis.hget(f"strategy:{sid}", "dag")
    dag_saved = json.loads(base64.b64decode(encoded).decode())
    assert any(n["node_type"] == "VersionSentinel" for n in dag_saved["nodes"])


@pytest.mark.asyncio
async def test_sentinel_skip(fake_redis):
    redis = fake_redis
    db = FakeDB()
    app = create_app(redis_client=redis, database=db, insert_sentinel=False, enable_background=False)
    with TestClient(app) as client:
        dag = {"nodes": []}
        payload = StrategySubmit(
            dag_json=base64.b64encode(json.dumps(dag).encode()).decode(),
            meta=None,
            node_ids_crc32=crc32_of_list([]),
        )
        resp = client.post("/strategies", json=payload.model_dump())
        assert resp.status_code == 202
        sid = resp.json()["strategy_id"]
        encoded = await redis.hget(f"strategy:{sid}", "dag")
        dag_saved = json.loads(base64.b64decode(encoded).decode())
        assert not any(
            n["node_type"] == "VersionSentinel" for n in dag_saved["nodes"]
        )
