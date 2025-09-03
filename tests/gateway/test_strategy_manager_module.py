import base64
import json

import pytest

from qmtl.gateway.redis_client import InMemoryRedis
from qmtl.gateway.database import MemoryDatabase
from qmtl.gateway.fsm import StrategyFSM
from qmtl.gateway.strategy_manager import StrategyManager
from qmtl.gateway.models import StrategySubmit


@pytest.mark.asyncio
async def test_strategy_manager_submit_and_status():
    redis = InMemoryRedis()
    db = MemoryDatabase()
    fsm = StrategyFSM(redis=redis, database=db)
    manager = StrategyManager(redis=redis, database=db, fsm=fsm, insert_sentinel=False)

    dag = {"nodes": []}
    payload = StrategySubmit(
        dag_json=base64.b64encode(json.dumps(dag).encode()).decode(),
        meta=None,
        node_ids_crc32=0,
    )
    sid, existed = await manager.submit(payload)
    assert not existed
    assert await manager.status(sid) == "queued"
