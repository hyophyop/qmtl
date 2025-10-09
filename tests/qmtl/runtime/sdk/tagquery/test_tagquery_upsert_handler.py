import pytest

from qmtl.runtime.sdk import TagQueryNode, MatchMode
from qmtl.runtime.sdk.tagquery_manager import TagQueryManager


@pytest.mark.asyncio
async def test_tagquery_upsert_initializes_node():
    node = TagQueryNode(["t"], interval="60s", period=1)
    mgr = TagQueryManager()
    mgr.register(node)
    await mgr.handle_message(
        {
            "event": "tagquery.upsert",
            "data": {
                "tags": ["t"],
                "interval": 60,
                "queues": [{"queue": "q1", "global": False}],
                "version": 1,
            },
        }
    )
    assert node.upstreams == ["q1"]
    assert node.pre_warmup
    key = (("t",), 60, MatchMode.ANY)
    assert mgr._last_queue_sets[key] == frozenset(["q1"])


@pytest.mark.asyncio
async def test_queue_update_preserves_node_identity():
    node = TagQueryNode(["t1", "t2"], interval="60s", period=1)
    original_id = node.node_id

    mgr = TagQueryManager()
    mgr.register(node)

    await mgr.handle_message(
        {
            "type": "queue_update",
            "data": {
                "tags": ["t2", "t1"],
                "interval": 60,
                "queues": [
                    {"queue": "q1", "global": False},
                    {"queue": "q2", "global": False},
                ],
                "match_mode": "any",
                "version": 1,
            },
        }
    )

    assert node.node_id == original_id
    assert node.upstreams == ["q1", "q2"]

    await mgr.handle_message(
        {
            "event": "queue_update",
            "data": {
                "tags": " t2 , t1 ",
                "interval": 60,
                "queues": [{"queue": "q2", "global": False}],
                "match_mode": "any",
                "version": 1,
            },
        }
    )

    assert node.node_id == original_id
    assert node.upstreams == ["q2"]
