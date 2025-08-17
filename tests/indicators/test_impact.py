import pytest

from qmtl.indicators import impact_node
from qmtl.sdk.cache_view import CacheView
from qmtl.sdk.node import SourceNode


def test_impact_node() -> None:
    volume = SourceNode(interval="1s", period=1, config={"id": "volume"})
    avg_volume = SourceNode(interval="1s", period=1, config={"id": "avg_volume"})
    depth = SourceNode(interval="1s", period=1, config={"id": "depth"})
    node = impact_node(volume, avg_volume, depth, beta=0.5)
    data = {
        volume.node_id: {1: [(0, 100.0)]},
        avg_volume.node_id: {1: [(0, 400.0)]},
        depth.node_id: {1: [(0, 10.0)]},
    }
    view = CacheView(data)
    result = node.compute_fn(view)
    expected = (100.0 / 400.0) ** 0.5 / (10.0 ** 0.5)
    assert result == pytest.approx(expected)
