from qmtl.transforms import rate_of_change
from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def test_rate_of_change_compute():
    src = Node(interval=1, period=3)
    node = rate_of_change(src, period=2)
    data = {src.node_id: {1: [(0, 1), (1, 3)]}}
    view = CacheView(data)
    assert node.compute_fn(view) == 2.0
