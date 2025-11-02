from qmtl.runtime.transforms import volume_features, avg_volume_node
from qmtl.runtime.sdk.node import SourceNode
from qmtl.runtime.sdk.cache_view import CacheView


def test_volume_features_compute():
    src = SourceNode(interval="1s", period=5)
    node = volume_features(src, period=3)
    data = {src.node_id: {1: [(0, 10), (1, 20), (2, 30)]}}
    view = CacheView(data)
    result = node.compute_fn(view)
    assert result == {"volume_hat": 20.0, "volume_std": (200/3) ** 0.5}


def test_avg_volume_node_compute():
    src = SourceNode(interval="1s", period=5)
    node = avg_volume_node(src, period=3)
    data = {src.node_id: {1: [(0, 10), (1, 20), (2, 30)]}}
    view = CacheView(data)
    result = node.compute_fn(view)
    assert result == 20.0
