import math
import pytest

from qmtl.runtime.transforms import depth_change_node, price_change
from qmtl.runtime.sdk.node import SourceNode
from qmtl.runtime.sdk.cache_view import CacheView

llrti_mod = pytest.importorskip("strategies.nodes.indicators.llrti")


def test_llrti_features_combine_for_expected_value():
    ob_src = SourceNode(interval="1s", period=2, config={"id": "ob"})
    price_src = SourceNode(interval="1s", period=2, config={"id": "price"})
    depth_node = depth_change_node(ob_src)
    price_node = price_change(price_src)

    order_book = [
        (0, {"bids": [(100, 1.0)], "asks": [(101, 1.0)]}),
        (1, {"bids": [(100, 1.5)], "asks": [(101, 1.5)]}),
    ]
    prices = [(0, 100.0), (1, 101.0)]
    data = {
        ob_src.node_id: {1: order_book},
        price_src.node_id: {1: prices},
    }
    view = CacheView(data)

    depth_change = depth_node.compute_fn(view)
    price_delta = price_node.compute_fn(view)

    assert depth_change == 1.0
    assert price_delta == 1.0

    llrti_node = getattr(llrti_mod, "llrti_node")
    features = llrti_node(
        {
            "depth_changes": [depth_change],
            "price_change": price_delta,
            "delta_t": 1,
            "delta": 0.5,
            "beta": (0.0, 1.0),
        }
    )
    assert features["llrti"] == 1.0
    assert features["hazard"] == pytest.approx(1.0 / (1.0 + math.exp(-1.0)))
