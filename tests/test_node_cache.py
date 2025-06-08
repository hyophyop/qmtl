import pytest
from qmtl.sdk import Node, StreamInput, Runner, NodeCache


def test_cache_warmup_and_compute():
    calls = []

    def fn(cache):
        calls.append(cache)

    src = StreamInput(interval=60, period=2)
    node = Node(input=src, compute_fn=fn, name="n", interval=60, period=2)

    Runner.feed_queue_data(node, "q1", 60, 60, {"v": 1})
    assert node.pre_warmup
    assert node.cache.snapshot()["q1"][60] == [(60, {"v": 1})]
    assert not calls

    Runner.feed_queue_data(node, "q1", 60, 120, {"v": 2})
    assert not node.pre_warmup
    assert node.cache.snapshot()["q1"][60] == [
        (60, {"v": 1}),
        (120, {"v": 2}),
    ]
    assert len(calls) == 1

    Runner.feed_queue_data(node, "q1", 60, 180, {"v": 3})
    assert node.cache.snapshot()["q1"][60] == [
        (120, {"v": 2}),
        (180, {"v": 3}),
    ]
    assert len(calls) == 2


def test_multiple_upstreams():
    calls = []

    def fn(cache):
        calls.append(cache)

    src = StreamInput(interval=60, period=2)
    node = Node(input=src, compute_fn=fn, name="n", interval=60, period=2)

    Runner.feed_queue_data(node, "u1", 60, 60, {"v": 1})
    Runner.feed_queue_data(node, "u2", 60, 60, {"v": 1})
    assert node.pre_warmup
    Runner.feed_queue_data(node, "u1", 60, 120, {"v": 2})
    assert node.pre_warmup
    Runner.feed_queue_data(node, "u2", 60, 120, {"v": 2})
    assert not node.pre_warmup
    assert len(calls) == 1
    snap = node.cache.snapshot()
    assert snap["u1"][60][-1][0] == 120
    assert snap["u2"][60][-1][0] == 120


def test_tensor_memory():
    cache = NodeCache(period=4)
    cache.append("u1", 60, 1, {"v": 1})
    expected = 1 * 1 * 4 * 2 * 8
    assert cache._tensor.nbytes == expected


def test_gap_detection():
    cache = NodeCache(period=2)
    cache.append("u1", 60, 1, {"v": 1})
    assert not cache.missing_flags()["u1"][60]
    cache.append("u1", 60, 3, {"v": 2})
    assert cache.missing_flags()["u1"][60]


def test_on_missing_policy_skip_and_fail():
    calls = []

    def fn(cache):
        calls.append(cache)

    src = StreamInput(interval=60, period=2)
    node = Node(input=src, compute_fn=fn, name="n", interval=60, period=2)

    Runner.feed_queue_data(node, "q1", 60, 1, {"v": 1})
    # Gap -> should skip
    Runner.feed_queue_data(node, "q1", 60, 3, {"v": 2}, on_missing="skip")
    assert node.cache.missing_flags()["q1"][60]
    assert len(calls) == 0

    node2 = Node(input=src, compute_fn=fn, name="n2", interval=60, period=2)
    Runner.feed_queue_data(node2, "q1", 60, 1, {"v": 1})
    with pytest.raises(RuntimeError):
        Runner.feed_queue_data(node2, "q1", 60, 3, {"v": 2}, on_missing="fail")

