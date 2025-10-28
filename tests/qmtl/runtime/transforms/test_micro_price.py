import math

from qmtl.runtime.transforms import (
    micro_price,
    micro_price_from_imbalance,
    micro_price_node,
    imbalance_to_weight,
)
from qmtl.runtime.sdk.node import SourceNode
from qmtl.runtime.sdk.cache_view import CacheView


def test_micro_price_function():
    assert micro_price(99.0, 101.0, 0.25) == 0.25 * 101.0 + 0.75 * 99.0


def test_micro_price_from_imbalance_linear():
    result = micro_price_from_imbalance(99.0, 101.0, 0.0, mode="linear")
    assert result == 100.0


def test_micro_price_node_with_weight():
    bid = SourceNode(interval="1s", period=1, config={"id": "bid"})
    ask = SourceNode(interval="1s", period=1, config={"id": "ask"})
    weight = SourceNode(interval="1s", period=1, config={"id": "w"})
    node = micro_price_node(bid, ask, weight_node=weight)
    data = {
        bid.node_id: {1: [(0, 99.0)]},
        ask.node_id: {1: [(0, 101.0)]},
        weight.node_id: {1: [(0, 0.75)]},
    }
    view = CacheView(data)
    assert node.compute_fn(view) == micro_price(99.0, 101.0, 0.75)


def test_micro_price_node_with_linear_imbalance():
    bid = SourceNode(interval="1s", period=1, config={"id": "bid"})
    ask = SourceNode(interval="1s", period=1, config={"id": "ask"})
    imbalance = SourceNode(interval="1s", period=1, config={"id": "imb"})
    node = micro_price_node(bid, ask, imbalance_node=imbalance, mode="linear")
    data = {
        bid.node_id: {1: [(0, 99.0)]},
        ask.node_id: {1: [(0, 101.0)]},
        imbalance.node_id: {1: [(0, 0.2)]},
    }
    view = CacheView(data)
    weight = imbalance_to_weight(0.2, mode="linear")
    expected = micro_price(99.0, 101.0, weight)
    assert view is not None
    assert node.compute_fn(view) == expected


def test_micro_price_node_with_logistic_imbalance():
    bid = SourceNode(interval="1s", period=1, config={"id": "bid"})
    ask = SourceNode(interval="1s", period=1, config={"id": "ask"})
    imbalance = SourceNode(interval="1s", period=1, config={"id": "imb"})
    node = micro_price_node(bid, ask, imbalance_node=imbalance, slope=4.0, clamp=0.8)
    data = {
        bid.node_id: {1: [(0, 100.0)]},
        ask.node_id: {1: [(0, 100.5)]},
        imbalance.node_id: {1: [(0, 0.6)]},
    }
    view = CacheView(data)
    weight = imbalance_to_weight(0.6, mode="logistic", slope=4.0, clamp=0.8)
    expected = micro_price(100.0, 100.5, weight)
    assert math.isclose(node.compute_fn(view), expected)


def test_micro_price_node_missing_weight():
    bid = SourceNode(interval="1s", period=1, config={"id": "bid"})
    ask = SourceNode(interval="1s", period=1, config={"id": "ask"})
    weight = SourceNode(interval="1s", period=1, config={"id": "w"})
    node = micro_price_node(bid, ask, weight_node=weight)
    data = {
        bid.node_id: {1: [(0, 99.0)]},
        ask.node_id: {1: [(0, 101.0)]},
        weight.node_id: {1: []},
    }
    view = CacheView(data)
    assert node.compute_fn(view) is None
