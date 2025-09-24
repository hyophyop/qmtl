import base64
import json

import pytest
from fastapi.testclient import TestClient

from qmtl.services.gateway.api import create_app, Database
from qmtl.services.gateway.models import StrategySubmit
from tests.runtime.sdk.factories import indicator_node_payload, node_ids_crc32


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


def test_checksum_rejects_tampered_ids(client):
    node_a = indicator_node_payload(
        code_hash="ch_a",
        config_hash="cfg_a",
        schema_hash="sch_a",
        schema_compat_id="sch_a_major",
        params={"window": 5},
    )
    node_b = indicator_node_payload(
        code_hash="ch_b",
        config_hash="cfg_b",
        schema_hash="sch_b",
        schema_compat_id="sch_b_major",
        params={"window": 10},
        dependencies=["dep-a"],
    )
    dag = {"nodes": [node_a, node_b]}
    checksum = node_ids_crc32(dag["nodes"])
    good = StrategySubmit(
        dag_json=base64.b64encode(json.dumps(dag).encode()).decode(),
        meta=None,
        node_ids_crc32=checksum,
    )
    resp = client.post("/strategies", json=good.model_dump())
    assert resp.status_code == 202

    tampered = {
        "nodes": [
            {**node_a, "node_id": "blake3:tampered"},
            node_b,
        ]
    }
    bad = StrategySubmit(
        dag_json=base64.b64encode(json.dumps(tampered).encode()).decode(),
        meta=None,
        node_ids_crc32=checksum,
    )
    resp2 = client.post("/strategies", json=bad.model_dump())
    assert resp2.status_code == 400
