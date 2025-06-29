import base64
import json

import pytest
from fastapi.testclient import TestClient

from qmtl.gateway.api import create_app, Database, StrategySubmit
from qmtl.common import crc32_of_list


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
    app = create_app(redis_client=fake_redis, database=db)
    return TestClient(app)


def test_checksum_rejects_tampered_ids(client):
    dag = {"nodes": [{"node_id": "A"}, {"node_id": "B"}]}
    checksum = crc32_of_list(["A", "B"])
    good = StrategySubmit(
        dag_json=base64.b64encode(json.dumps(dag).encode()).decode(),
        meta=None,
        run_type="dry-run",
        node_ids_crc32=checksum,
    )
    resp = client.post("/strategies", json=good.model_dump())
    assert resp.status_code == 202

    tampered = {"nodes": [{"node_id": "X"}, {"node_id": "B"}]}
    bad = StrategySubmit(
        dag_json=base64.b64encode(json.dumps(tampered).encode()).decode(),
        meta=None,
        run_type="dry-run",
        node_ids_crc32=checksum,
    )
    resp2 = client.post("/strategies", json=bad.model_dump())
    assert resp2.status_code == 400
