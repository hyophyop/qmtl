from qmtl.sdk import TagQueryNode


def test_update_queues():
    node = TagQueryNode(["t1"], interval=60, period=2)
    node.update_queues(["q1", "q2"])
    assert node.upstreams == ["q1", "q2"]
    assert node.execute

    node.update_queues([])
    assert node.upstreams == []
    assert not node.execute
