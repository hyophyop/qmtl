import base64
import json

from fastapi.testclient import TestClient

from qmtl.services.gateway.api import create_app, Database
from qmtl.services.gateway.models import StrategySubmit
from qmtl.services.gateway.routes.strategies import _ack_from_result
from qmtl.services.gateway.strategy_submission import StrategySubmissionResult
from qmtl.services.dagmanager.kafka_admin import partition_key, compute_key
from qmtl.foundation.proto import dagmanager_pb2
from tests.qmtl.runtime.sdk.factories import node_ids_crc32, tag_query_node_payload


_TAGQUERY_NODE = tag_query_node_payload(
    tags=["t1"],
    interval=60,
    period=0,
    code_hash="c",
    config_hash="cfg",
    schema_hash="s",
    schema_compat_id="s-major",
)
_TAGQUERY_NODE_ID = _TAGQUERY_NODE["node_id"]


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
            _TAGQUERY_NODE_ID: [
                {"queue": "q1", "global": False},
                {"queue": "q2", "global": False},
            ]
        }

    async def get_queues_by_tag(
        self, tags, interval, match_mode="any", world_id=None, execution_domain=None
    ):
        # Mirror the diff-produced topics
        return list(self._queues.get(_TAGQUERY_NODE_ID, []))

    async def diff(self, strategy_id: str, dag_json: str, *, world_id: str | None = None):
        # Return a single-chunk result mapping to topics used above
        decoded = json.loads(base64.b64decode(dag_json).decode())
        crc = node_ids_crc32(decoded.get("nodes", []))
        return dagmanager_pb2.DiffChunk(
            queue_map={
                partition_key(
                    _TAGQUERY_NODE_ID,
                    0,
                    0,
                    compute_key=compute_key(_TAGQUERY_NODE_ID),
                ): "q1",
                partition_key(
                    _TAGQUERY_NODE_ID,
                    0,
                    1,
                    compute_key=compute_key(_TAGQUERY_NODE_ID),
                ): "q2",
            },
            sentinel_id="s-123",
            crc32=crc,
        )

    async def close(self):
        pass


def _payload_for(dag: dict) -> StrategySubmit:
    return StrategySubmit(
        dag_json=base64.b64encode(json.dumps(dag).encode()).decode(),
        meta=None,
        node_ids_crc32=node_ids_crc32(dag.get("nodes", [])),
    )


def test_ack_from_result_copies_submission_result_fields():
    result = StrategySubmissionResult(
        strategy_id="s-1",
        queue_map={"node": [{"queue": "q", "global": False}]},
        sentinel_id="sentinel",
        node_ids_crc32=1234,
        downgraded=True,
        downgrade_reason="missing-context",
        safe_mode=True,
    )

    ack = _ack_from_result(result)

    assert ack.model_dump() == {
        "strategy_id": "s-1",
        "queue_map": {"node": [{"queue": "q", "global": False}]},
        "sentinel_id": "sentinel",
        "node_ids_crc32": 1234,
        "downgraded": True,
        "downgrade_reason": "missing-context",
        "safe_mode": True,
    }


def test_dry_run_matches_submit_queue_map_and_sentinel(fake_redis):
    dag_client = DummyDagClient()
    app = create_app(redis_client=fake_redis, database=FakeDB(), dag_client=dag_client, enable_background=False)
    with TestClient(app) as c:
        dag = {"nodes": [tag_query_node_payload(
            tags=["t1"],
            interval=60,
            period=0,
            code_hash="c",
            config_hash="cfg",
            schema_hash="s",
            schema_compat_id="s-major",
            inputs=[],
        )]}
        payload = _payload_for(dag)

        dry = c.post("/strategies/dry-run", json=payload.model_dump())
        assert dry.status_code == 200
        submit = c.post("/strategies", json=payload.model_dump())
        assert submit.status_code == 202

        dry_payload = dry.json()
        submit_payload = submit.json()

        dq = dry_payload["queue_map"]
        sq = submit_payload["queue_map"]
        # Compare ignoring order of queues per node
        def _norm(m: dict[str, list[dict]]):
            return {k: sorted(v, key=lambda x: (bool(x.get("global")), x.get("queue"))) for k, v in m.items()}
        assert _norm(dq) == _norm(sq)
        # sentinel_id should be present in both responses
        assert "sentinel_id" in dry_payload
        assert "sentinel_id" in submit_payload

        assert set(dry_payload) == set(submit_payload)
        for key in ("node_ids_crc32", "downgraded", "downgrade_reason", "safe_mode"):
            assert dry_payload[key] == submit_payload[key]
