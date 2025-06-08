from qmtl.sdk import Node, StreamInput, Runner


def test_cache_warmup_and_compute():
    calls = []

    def fn(cache):
        calls.append(cache)

    src = StreamInput(interval=60, period=2)
    node = Node(input=src, compute_fn=fn, name="n", interval=60, period=2)

    Runner.feed_queue_data(node, "q1", 60, 1, {"v": 1})
    assert node.pre_warmup
    assert len(node.cache["q1"][60]) == 1
    assert not calls

    Runner.feed_queue_data(node, "q1", 60, 2, {"v": 2})
    assert not node.pre_warmup
    assert len(node.cache["q1"][60]) == 2
    assert len(calls) == 1

    Runner.feed_queue_data(node, "q1", 60, 3, {"v": 3})
    assert len(node.cache["q1"][60]) == 2
    assert len(calls) == 2


def test_multiple_upstreams():
    calls = []

    def fn(cache):
        calls.append(cache)

    src = StreamInput(interval=60, period=2)
    node = Node(input=src, compute_fn=fn, name="n", interval=60, period=2)

    Runner.feed_queue_data(node, "u1", 60, 1, {"v": 1})
    Runner.feed_queue_data(node, "u2", 60, 1, {"v": 1})
    assert node.pre_warmup
    Runner.feed_queue_data(node, "u1", 60, 2, {"v": 2})
    assert node.pre_warmup
    Runner.feed_queue_data(node, "u2", 60, 2, {"v": 2})
    assert not node.pre_warmup
    assert len(calls) == 1

