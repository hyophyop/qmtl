from qmtl.transforms import rate_of_change, stochastic, angle
from qmtl.sdk.node import SourceNode
from qmtl.sdk.cache_view import CacheView


def test_rate_of_change_compute():
    src = SourceNode(interval="1s", period=3)
    node = rate_of_change(src, period=2)
    data = {src.node_id: {1: [(0, 1), (1, 3)]}}
    view = CacheView(data)
    assert node.compute_fn(view) == 2.0


def test_stochastic_compute():
    src = SourceNode(interval="1s", period=3)
    node = stochastic(src, period=3)
    data = {src.node_id: {1: [(0, 1), (1, 2), (2, 3)]}}
    view = CacheView(data)
    assert node.compute_fn(view) == 100.0


def test_angle_compute():
    src = SourceNode(interval="1s", period=3)
    node = angle(src, period=3)
    data = {src.node_id: {1: [(0, 1), (1, 2), (2, 3)]}}
    view = CacheView(data)
    assert round(node.compute_fn(view), 2) == 45.0
