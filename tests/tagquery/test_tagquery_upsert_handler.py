import pytest

from qmtl.sdk import TagQueryNode, MatchMode
from qmtl.sdk.tagquery_manager import TagQueryManager


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
            },
        }
    )
    assert node.upstreams == ["q1"]
    assert node.pre_warmup
    key = (("t",), 60, MatchMode.ANY)
    assert mgr._last_queue_sets[key] == frozenset(["q1"])
