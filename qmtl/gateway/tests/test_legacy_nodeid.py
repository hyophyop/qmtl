import base64
import json
from typing import Any

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from qmtl.common import compute_node_id, crc32_of_list
from qmtl.gateway import metrics as gw_metrics
from qmtl.gateway.api import create_app, Database
from qmtl.gateway.models import StrategySubmit
from qmtl.gateway.routes import (
    LEGACY_NODEID_SUNSET,
    LEGACY_NODEID_WARNING_HEADER,
)
from fakeredis.aioredis import FakeRedis


class _MemoryDB(Database):
    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        self._events: list[tuple[str, str]] = []

    async def insert_strategy(self, strategy_id: str, meta=None) -> None:  # pragma: no cover - unused
        self._records[strategy_id] = {"status": "queued", "meta": meta}

    async def append_event(self, strategy_id: str, event: str) -> None:  # pragma: no cover - unused
        self._events.append((strategy_id, event))


class _StubHub:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def send_deprecation_notice(self, payload: dict) -> None:
        self.events.append(payload)

    async def start(self, *, start_server: bool = False) -> int:  # pragma: no cover - unused
        return 0

    async def stop(self) -> None:  # pragma: no cover - unused
        return None


@pytest_asyncio.fixture
async def fake_redis():
    redis = FakeRedis(decode_responses=True)
    try:
        yield redis
    finally:
        if hasattr(redis, "aclose"):
            await redis.aclose(close_connection_pool=True)
        else:
            await redis.close()


def _legacy_payload() -> tuple[StrategySubmit, str]:
    node = {
        "node_type": "N",
        "code_hash": "c",
        "config_hash": "cfg",
        "schema_hash": "s",
        "schema_id": "schema:v1",
        "interval": 60,
        "period": 5,
        "params": {"window": 5},
    }
    legacy_id = compute_node_id(
        node["node_type"], node["code_hash"], node["config_hash"], node["schema_hash"]
    )
    node["node_id"] = legacy_id
    dag = {"nodes": [node]}
    payload = StrategySubmit(
        dag_json=base64.b64encode(json.dumps(dag).encode()).decode(),
        meta=None,
        node_ids_crc32=crc32_of_list([legacy_id]),
    )
    return payload, legacy_id


@pytest.mark.asyncio
async def test_legacy_nodeid_response_headers(fake_redis):
    gw_metrics.reset_metrics()
    payload, legacy_id = _legacy_payload()
    db = _MemoryDB()
    app = create_app(redis_client=fake_redis, database=db, enable_background=False)
    with TestClient(app) as client:
        resp = client.post("/strategies", json=payload.model_dump())
        assert resp.status_code == 202
        warning = resp.headers.get("Warning")
        assert warning and LEGACY_NODEID_WARNING_HEADER in warning
        assert resp.headers.get("Deprecation") == "true"
        assert resp.headers.get("Sunset") == LEGACY_NODEID_SUNSET
        snapshot = gw_metrics.get_last_legacy_nodeid_strategy()
        assert legacy_id in (snapshot.get("node_ids") or [])


@pytest.mark.asyncio
async def test_legacy_nodeid_ws_notice(fake_redis):
    gw_metrics.reset_metrics()
    payload, legacy_id = _legacy_payload()
    hub = _StubHub()
    db = _MemoryDB()
    app = create_app(
        redis_client=fake_redis,
        database=db,
        ws_hub=hub,
        enable_background=False,
    )
    with TestClient(app) as client:
        resp = client.post("/strategies", json=payload.model_dump())
        assert resp.status_code == 202
        strategy_id = resp.json()["strategy_id"]
    assert hub.events, "expected a deprecation notice via WebSocket hub"
    notice = hub.events[0]
    assert notice.get("strategy_id") == strategy_id
    assert legacy_id in (notice.get("node_ids") or [])
    assert notice.get("sunset") == LEGACY_NODEID_SUNSET
    assert notice.get("message")
    assert notice.get("nodes")
