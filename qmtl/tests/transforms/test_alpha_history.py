from qmtl.transforms import alpha_history_node
from qmtl.sdk.node import SourceNode
from qmtl.sdk.cache_view import CacheView


def test_alpha_history_sliding_window():
    src = SourceNode(interval="1s", period=1)
    node = alpha_history_node(src, window=3)

    view1 = CacheView({src.node_id: {1: [(0, 1)]}})
    assert node.compute_fn(view1) == [1]

    view2 = CacheView({src.node_id: {1: [(1, 2)]}})
    assert node.compute_fn(view2) == [1, 2]

    view3 = CacheView({src.node_id: {1: [(2, 3)]}})
    assert node.compute_fn(view3) == [1, 2, 3]

    view4 = CacheView({src.node_id: {1: [(3, 4)]}})
    assert node.compute_fn(view4) == [2, 3, 4]


def test_alpha_history_select_fn_returns():
    src = SourceNode(interval="1s", period=1)
    node = alpha_history_node(
        src, window=2, select_fn=lambda payload: payload["return"]
    )

    view1 = CacheView({src.node_id: {1: [(0, {"alpha": 1.0, "return": 0.0})]}})
    assert node.compute_fn(view1) == [0.0]

    view2 = CacheView({src.node_id: {1: [(1, {"alpha": 1.1, "return": 0.1})]}})
    assert node.compute_fn(view2) == [0.0, 0.1]

    view3 = CacheView({src.node_id: {1: [(2, {"alpha": 1.0, "return": -0.1})]}})
    assert node.compute_fn(view3) == [0.1, -0.1]

