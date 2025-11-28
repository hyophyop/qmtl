import base64
import json

import pytest
from fastapi.testclient import TestClient

from qmtl.foundation.common import compute_node_id, crc32_of_list
from qmtl.services.gateway.api import create_app, Database
from qmtl.services.gateway.models import StrategySubmit


class FakeDB(Database):
    def __init__(self) -> None:
        self.records: dict[str, dict[str, object]] = {}
        self.events: list[tuple[str, str]] = []

    async def insert_strategy(self, strategy_id: str, meta=None) -> None:  # pragma: no cover - not used
        self.records[strategy_id] = {"status": "queued", "meta": meta}

    async def set_status(self, strategy_id: str, status: str) -> None:  # pragma: no cover - not used
        self.records[strategy_id]["status"] = status

    async def get_status(self, strategy_id: str) -> str | None:  # pragma: no cover - not used
        rec = self.records.get(strategy_id)
        if rec is None:
            return None
        status = rec.get("status")
        return status if isinstance(status, str) else None

    async def append_event(self, strategy_id: str, event: str) -> None:  # pragma: no cover - not used
        self.events.append((strategy_id, event))


@pytest.fixture
def client_and_redis(fake_redis):
    db = FakeDB()
    app = create_app(redis_client=fake_redis, database=db, enable_background=False)
    with TestClient(app) as c:
        yield c, fake_redis


def _payload_for(node: dict) -> StrategySubmit:
    dag = {"schema_version": "v1", "nodes": [node]}
    return StrategySubmit(
        dag_json=base64.b64encode(json.dumps(dag).encode()).decode(),
        meta=None,
        node_ids_crc32=crc32_of_list([node.get("node_id", "")]),
    )


def test_compute_node_id_collision():
    node = {
        "node_type": "A",
        "code_hash": "B",
        "config_hash": "C",
        "schema_hash": "D",
        "schema_compat_id": "D-major",
        "params": {"alpha": 1},
        "interval": 1,
        "period": 0,
        "dependencies": ["dep-1"],
    }
    first = compute_node_id(node)
    second = compute_node_id(node, existing_ids={first})
    assert first != second
    assert second.startswith("blake3:")


@pytest.mark.asyncio
async def test_node_id_mismatch(client_and_redis):
    client, _ = client_and_redis
    node = {
        "node_type": "N",
        "code_hash": "c",
        "config_hash": "cfg",
        "schema_hash": "s",
        "schema_compat_id": "s-compat",
        "params": {},
        "dependencies": [],
        "node_id": "wrong",
    }
    payload = _payload_for(node)
    resp = client.post("/strategies", json=payload.model_dump())
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "E_NODE_ID_MISMATCH"
    assert detail["node_id_mismatch"][0]["expected"].startswith("blake3:")
    assert "hint" in detail


@pytest.mark.asyncio
async def test_missing_node_fields_rejected(client_and_redis):
    client, _ = client_and_redis
    node = {
        "node_type": "N",
        "code_hash": "c",
        # config_hash intentionally omitted
        "schema_hash": "s",
        "node_id": "blake3:deadbeef",
        "params": {},
        "dependencies": [],
    }
    payload = _payload_for(node)
    resp = client.post("/strategies", json=payload.model_dump())
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "E_NODE_ID_FIELDS"
    missing = detail["missing_fields"][0]
    missing_fields = set(missing["missing"])
    assert "config_hash" in missing_fields
    assert "schema_compat_id" in missing_fields
    assert "hint" in detail


@pytest.mark.asyncio
async def test_legacy_node_id_rejected(client_and_redis):
    client, _ = client_and_redis
    legacy_like = "legacy:world"
    node = {
        "node_type": "N",
        "code_hash": "c",
        "config_hash": "cfg",
        "schema_hash": "s",
        "schema_compat_id": "s-compat",
        "params": {},
        "dependencies": [],
        "node_id": legacy_like,
    }
    payload = StrategySubmit(
        dag_json=base64.b64encode(json.dumps({"schema_version": "v1", "nodes": [node]}).encode()).decode(),
        meta=None,
        world_id="w1",
        node_ids_crc32=crc32_of_list([legacy_like]),
    )
    resp = client.post("/strategies", json=payload.model_dump())
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "E_NODE_ID_MISMATCH"


@pytest.mark.asyncio
async def test_tag_query_node_id_mismatch(client_and_redis):
    client, _ = client_and_redis
    node = {
        "node_type": "TagQueryNode",
        "code_hash": "c",
        "config_hash": "cfg",
        "schema_hash": "s",
        "schema_compat_id": "s-compat",
        "params": {"tags": ["t1"], "match_mode": "any"},
        "dependencies": [],
        "tags": ["t1"],
        "interval": 60,
        "node_id": "incorrect",
    }
    payload = _payload_for(node)
    resp = client.post("/strategies", json=payload.model_dump())
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "E_NODE_ID_MISMATCH"


@pytest.mark.asyncio
async def test_sentinel_inserted(client_and_redis):
    client, redis = client_and_redis
    dag = {"schema_version": "v1", "nodes": []}
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
    app = create_app(
        redis_client=redis, database=db, insert_sentinel=False, enable_background=False
    )
    with TestClient(app) as client:
        dag = {"schema_version": "v1", "nodes": []}
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
