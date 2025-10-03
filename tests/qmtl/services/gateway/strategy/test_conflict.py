import base64
import json

import pytest
from fastapi.testclient import TestClient

from qmtl.services.gateway.api import create_app, Database
from qmtl.services.gateway.models import StrategySubmit
from tests.qmtl.runtime.sdk.factories import indicator_node_payload, node_ids_crc32


class FakeDB(Database):
    async def insert_strategy(self, strategy_id: str, meta):
        pass

    async def set_status(self, strategy_id: str, status: str):
        pass

    async def get_status(self, strategy_id: str):
        return "queued"

    async def append_event(self, strategy_id: str, event: str):
        pass


@pytest.fixture
def client(fake_redis):
    db = FakeDB()
    app = create_app(redis_client=fake_redis, database=db, enable_background=False)
    with TestClient(app) as c:
        yield c


def make_payload(dag: dict) -> StrategySubmit:
    return StrategySubmit(
        dag_json=base64.b64encode(json.dumps(dag).encode()).decode(),
        meta=None,
        node_ids_crc32=node_ids_crc32(dag.get("nodes", [])),
    )


def test_duplicate_strategy_returns_409(client):
    node = indicator_node_payload(
        code_hash="ch",
        config_hash="cfg",
        schema_hash="sh",
        schema_compat_id="sh-major",
        params={"window": 5},
    )
    dag = {"nodes": [node]}
    payload = make_payload(dag)
    first = client.post("/strategies", json=payload.model_dump())
    assert first.status_code == 202

    second = client.post("/strategies", json=payload.model_dump())
    assert second.status_code == 409
    assert second.json()["detail"]["strategy_id"] == first.json()["strategy_id"]
