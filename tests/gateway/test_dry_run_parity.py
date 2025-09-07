import base64
import json

from fastapi.testclient import TestClient

from qmtl.gateway.api import create_app, Database
from qmtl.gateway.models import StrategySubmit
from qmtl.common import crc32_of_list
from qmtl.proto import dagmanager_pb2


class FakeDB(Database):
    async def insert_strategy(self, strategy_id: str, meta):
        pass

    async def set_status(self, strategy_id: str, status: str):
        pass

    async def get_status(self, strategy_id: str):
        return "queued"

    async def append_event(self, strategy_id: str, event: str):
        pass


class DummyDagClient:
    def __init__(self):
        self._queues = {
            "N1": [
                {"queue": "q1", "global": False},
                {"queue": "q2", "global": False},
            ]
        }

    async def get_queues_by_tag(self, tags, interval, match_mode="any", world_id=None):
        # Mirror the diff-produced topics
        return list(self._queues.get("N1", []))

    async def diff(self, strategy_id: str, dag_json: str, *, world_id: str | None = None):
        # Return a single-chunk result mapping to topics used above
        return dagmanager_pb2.DiffChunk(
            queue_map={"N1:0:0": "q1", "N1:0:1": "q2"},
            sentinel_id="s-123",
        )

    async def close(self):
        pass


def _payload_for(dag: dict) -> StrategySubmit:
    return StrategySubmit(
        dag_json=base64.b64encode(json.dumps(dag).encode()).decode(),
        meta=None,
        node_ids_crc32=crc32_of_list(n.get("node_id") for n in dag.get("nodes", [])),
    )


def test_dry_run_matches_submit_queue_map_and_sentinel(fake_redis):
    dag_client = DummyDagClient()
    app = create_app(redis_client=fake_redis, database=FakeDB(), dag_client=dag_client, enable_background=False)
    with TestClient(app) as c:
        dag = {
            "nodes": [
                {
                    "node_id": "N1",
                    "node_type": "TagQueryNode",
                    "interval": 60,
                    "tags": ["t1"],
                    "code_hash": "c",
                    "schema_hash": "s",
                    "inputs": [],
                }
            ]
        }
        payload = _payload_for(dag)

        dry = c.post("/strategies/dry-run", json=payload.model_dump())
        assert dry.status_code == 200
        submit = c.post("/strategies", json=payload.model_dump())
        assert submit.status_code == 202

        dq = dry.json()["queue_map"]
        sq = submit.json()["queue_map"]
        # Compare ignoring order of queues per node
        def _norm(m: dict[str, list[dict]]):
            return {k: sorted(v, key=lambda x: (bool(x.get("global")), x.get("queue"))) for k, v in m.items()}
        assert _norm(dq) == _norm(sq)
        # sentinel_id should be present in both responses
        assert "sentinel_id" in dry.json()
        assert "sentinel_id" in submit.json()
