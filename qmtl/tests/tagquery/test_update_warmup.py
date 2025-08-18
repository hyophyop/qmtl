import pytest

from qmtl.sdk import TagQueryNode, Runner
from qmtl.sdk.tagquery_manager import TagQueryManager


@pytest.mark.asyncio
async def test_update_warmup_and_removal():
    calls = []
    node = TagQueryNode(["t"], interval="60s", period=2, compute_fn=lambda v: calls.append(v))
    manager = TagQueryManager()
    manager.register(node)

    # Initial queue registration
    await manager.handle_message({
        "event": "queue_update",
        "data": {"tags": ["t"], "interval": 60, "queues": ["q1"], "match_mode": "any"},
    })
    assert node.upstreams == ["q1"]
    assert node.pre_warmup

    # Warm up node
    Runner.feed_topic_data(node, "q1", 60, 60, {"v": 1})
    assert node.pre_warmup
    Runner.feed_topic_data(node, "q1", 60, 120, {"v": 2})
    assert not node.pre_warmup
    assert len(calls) == 1

    # Add new queue and ensure warmup resets
    await manager.handle_message({
        "event": "queue_update",
        "data": {"tags": ["t"], "interval": 60, "queues": ["q1", "q2"], "match_mode": "any"},
    })
    assert set(node.upstreams) == {"q1", "q2"}
    assert node.pre_warmup

    Runner.feed_topic_data(node, "q2", 60, 180, {"v": 3})
    assert node.pre_warmup
    Runner.feed_topic_data(node, "q2", 60, 240, {"v": 4})
    assert not node.pre_warmup
    assert len(calls) == 2

    # Remove queue and validate cache drop
    await manager.handle_message({
        "event": "queue_update",
        "data": {"tags": ["t"], "interval": 60, "queues": ["q2"], "match_mode": "any"},
    })
    assert node.upstreams == ["q2"]
    assert node.cache.get_slice("q1", 60, count=1) == []
