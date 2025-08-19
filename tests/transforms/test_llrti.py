from qmtl.transforms import depth_change_node, price_change, llrti
from qmtl.sdk.node import SourceNode
from qmtl.sdk.cache_view import CacheView


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

    index = llrti([depth_change], price_delta, 1, 0.5)
    assert index == 1.0
