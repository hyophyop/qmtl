from qmtl.indicators import sma
from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def test_sma_compute():
    src = Node(interval=1, period=3)
    node = sma(src, window=2)
    data = {src.node_id: {1: [(0, 1), (1, 3)]}}
    view = CacheView(data)
    assert node.compute_fn(view) == 2

