from qmtl.transforms import volume_features
from qmtl.sdk.node import SourceNode
from qmtl.sdk.cache_view import CacheView


def test_volume_features_compute():
    src = SourceNode(interval="1s", period=5)
    node = volume_features(src, period=3)
    data = {src.node_id: {1: [(0, 10), (1, 20), (2, 30)]}}
    view = CacheView(data)
    result = node.compute_fn(view)
    assert result == {"volume_hat": 20.0, "volume_std": (200/3) ** 0.5}
