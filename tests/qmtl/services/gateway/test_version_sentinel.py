import base64
import json

import pytest

from qmtl.services.gateway.database import MemoryDatabase
from qmtl.services.gateway.fsm import StrategyFSM
from qmtl.services.gateway.models import StrategySubmit
from qmtl.services.gateway.redis_client import InMemoryRedis
from qmtl.services.gateway.strategy_manager import StrategyManager


@pytest.mark.asyncio
async def test_gateway_auto_inserts_version_sentinel_with_metadata() -> None:
    redis = InMemoryRedis()
    db = MemoryDatabase()
    fsm = StrategyFSM(redis=redis, database=db)
    manager = StrategyManager(redis=redis, database=db, fsm=fsm)

    dag = {
        "nodes": [
            {
                "node_id": "node-a",
                "node_type": "Compute",
                "code_hash": "abc123",
                "schema_hash": "schema-1",
            }
        ]
    }
    dag_json = base64.b64encode(json.dumps(dag).encode()).decode()
    payload = StrategySubmit(
        dag_json=dag_json,
        meta={"strategy_version": "release-2025.10"},
        world_id="world-main",
        node_ids_crc32=0,
    )

    strategy_id, existed = await manager.submit(payload)

    assert not existed
    stored = await redis.hget(f"strategy:{strategy_id}", "dag")
    assert stored is not None
    decoded = json.loads(base64.b64decode(stored).decode())

    sentinels = [
        node for node in decoded.get("nodes", []) if node.get("node_type") == "VersionSentinel"
    ]
    assert len(sentinels) == 1
    sentinel = sentinels[0]
    assert sentinel["node_id"] == f"{strategy_id}-sentinel"
    assert sentinel["version"] == "release-2025.10"
    assert decoded["nodes"][0]["node_id"] == "node-a"

