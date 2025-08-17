from qmtl.transforms import depth_node
from qmtl.sdk.node import SourceNode
from qmtl.sdk.cache_view import CacheView


def test_depth_node_compute():
    src = SourceNode(interval="1s", period=5)
    node = depth_node(src, levels=2)
    snapshot = {
        "bids": [(100, 1.0), (99, 2.0), (98, 3.0)],
        "asks": [(101, 1.5), (102, 2.5)],
    }
    data = {src.node_id: {1: [(0, snapshot)]}}
    view = CacheView(data)
    result = node.compute_fn(view)
    assert result == {"bid_depth": 3.0, "ask_depth": 4.0}
