import math

from qmtl.runtime.transforms import (
    order_book_imbalance_node,
    logistic_order_book_imbalance_node,
    imbalance_to_weight,
    rate_of_change,
)
from qmtl.runtime.sdk.node import SourceNode
from qmtl.runtime.sdk.cache_view import CacheView


def test_order_book_imbalance_compute():
    bid = SourceNode(interval="1s", period=1, config={"id": "bid"})
    ask = SourceNode(interval="1s", period=1, config={"id": "ask"})
    node = order_book_imbalance_node(bid, ask)
    data = {
        bid.node_id: {1: [(0, 10)]},
        ask.node_id: {1: [(0, 5)]},
    }
    view = CacheView(data)
    assert node.compute_fn(view) == (10 - 5) / (10 + 5)


def test_order_book_imbalance_derivative():
    bid = SourceNode(interval="1s", period=2, config={"id": "bid"})
    ask = SourceNode(interval="1s", period=2, config={"id": "ask"})
    obi = order_book_imbalance_node(bid, ask)
    derivative = rate_of_change(obi, period=2)

    view0 = CacheView({
        bid.node_id: {1: [(0, 10)]},
        ask.node_id: {1: [(0, 5)]},
    })
    obi0 = obi.compute_fn(view0)

    view1 = CacheView({
        bid.node_id: {1: [(0, 10), (1, 20)]},
        ask.node_id: {1: [(0, 5), (1, 15)]},
    })
    obi1 = obi.compute_fn(view1)

    roc_view = CacheView({obi.node_id: {1: [(0, obi0), (1, obi1)]}})
    assert derivative.compute_fn(roc_view) == (obi1 - obi0) / obi0


def test_logistic_order_book_weight_node():
    bid = SourceNode(interval="1s", period=1, config={"id": "bid"})
    ask = SourceNode(interval="1s", period=1, config={"id": "ask"})
    node = logistic_order_book_imbalance_node(bid, ask, slope=3.0)
    data = {
        bid.node_id: {1: [(0, 12.0)]},
        ask.node_id: {1: [(0, 8.0)]},
    }
    view = CacheView(data)
    imbalance = (12.0 - 8.0) / (12.0 + 8.0)
    expected = imbalance_to_weight(imbalance, mode="logistic", slope=3.0)
    assert node.compute_fn(view) == expected


def test_logistic_order_book_weight_clamp():
    bid = SourceNode(interval="1s", period=1, config={"id": "bid"})
    ask = SourceNode(interval="1s", period=1, config={"id": "ask"})
    node = logistic_order_book_imbalance_node(bid, ask, clamp=0.5, slope=10.0)
    data = {
        bid.node_id: {1: [(0, 1000.0)]},
        ask.node_id: {1: [(0, 1.0)]},
    }
    view = CacheView(data)
    imbalance = (1000.0 - 1.0) / (1000.0 + 1.0)
    expected = imbalance_to_weight(imbalance, mode="logistic", slope=10.0, clamp=0.5)
    result = node.compute_fn(view)
    assert math.isclose(result, expected)
