from qmtl.sdk import StreamInput, ProcessingNode, Runner


def _compute(view):
    return list(view.keys())


def test_node_with_string_interval_behaves_like_int():
    src_str = StreamInput(interval="1m", period=2)
    node_str = ProcessingNode(input=src_str, compute_fn=_compute, name="n", interval="1m", period=2)

    src_int = StreamInput(interval=60, period=2)
    node_int = ProcessingNode(input=src_int, compute_fn=_compute, name="n", interval=60, period=2)

    Runner.feed_topic_data(node_str, "q", 60, 60, {"v": 1})
    Runner.feed_topic_data(node_int, "q", 60, 60, {"v": 1})

    assert src_str.interval == src_int.interval == 60
    assert node_str.interval == node_int.interval == 60
    assert node_str.cache.get_slice("q", 60, count=1) == node_int.cache.get_slice("q", 60, count=1)
