import math

from qmtl.runtime.transforms import (
    gap_depth_weighted_sum_node,
    order_flow_imbalance_node,
    spread_zscore_node,
    hazard_node,
)
from qmtl.runtime.sdk.node import SourceNode
from qmtl.runtime.sdk.cache_view import CacheView


def test_gap_depth_weighted_sum_node():
    bid_p = SourceNode(interval="1s", period=1, config={"id": "bp"})
    ask_p = SourceNode(interval="1s", period=1, config={"id": "ap"})
    bid_v = SourceNode(interval="1s", period=1, config={"id": "bv"})
    ask_v = SourceNode(interval="1s", period=1, config={"id": "av"})
    node = gap_depth_weighted_sum_node(bid_p, ask_p, bid_v, ask_v)
    data = {
        bid_p.node_id: {1: [(0, [99, 98])]},
        ask_p.node_id: {1: [(0, [101, 102])]},
        bid_v.node_id: {1: [(0, [8, 3])]},
        ask_v.node_id: {1: [(0, [10, 5])]},
    }
    view = CacheView(data)
    expected = ((101 - 99) * (10 + 8) + (102 - 98) * (5 + 3)) / ((10 + 8) + (5 + 3))
    assert node.compute_fn(view) == expected


def test_order_flow_imbalance_node_nan():
    buy = SourceNode(interval="1s", period=1, config={"id": "buy"})
    sell = SourceNode(interval="1s", period=1, config={"id": "sell"})
    node = order_flow_imbalance_node(buy, sell)
    data = {buy.node_id: {1: [(0, math.nan)]}, sell.node_id: {1: [(0, 5)]}}
    view = CacheView(data)
    assert node.compute_fn(view) is None


def test_order_flow_imbalance_node():
    buy = SourceNode(interval="1s", period=1, config={"id": "buy"})
    sell = SourceNode(interval="1s", period=1, config={"id": "sell"})
    node = order_flow_imbalance_node(buy, sell)
    data = {buy.node_id: {1: [(0, 7)]}, sell.node_id: {1: [(0, 3)]}}
    view = CacheView(data)
    assert node.compute_fn(view) == (7 - 3) / (7 + 3)


def test_spread_zscore_node():
    bid = SourceNode(interval="1s", period=3, config={"id": "bid"})
    ask = SourceNode(interval="1s", period=3, config={"id": "ask"})
    node = spread_zscore_node(bid, ask, period=3)
    data = {
        bid.node_id: {1: [(0, 99), (1, 100), (2, 101)]},
        ask.node_id: {1: [(0, 100), (1, 102), (2, 104)]},
    }
    view = CacheView(data)
    expected = (3 - 2) / math.sqrt(2 / 3)
    assert node.compute_fn(view) == expected


def test_hazard_node_invalid():
    events = SourceNode(interval="1s", period=1, config={"id": "e"})
    pop = SourceNode(interval="1s", period=1, config={"id": "p"})
    node = hazard_node(events, pop)
    data = {events.node_id: {1: [(0, 1)]}, pop.node_id: {1: [(0, 0)]}}
    view = CacheView(data)
    assert node.compute_fn(view) is None


def test_hazard_node():
    events = SourceNode(interval="1s", period=1, config={"id": "e"})
    pop = SourceNode(interval="1s", period=1, config={"id": "p"})
    node = hazard_node(events, pop)
    data = {events.node_id: {1: [(0, 2)]}, pop.node_id: {1: [(0, 100)]}}
    view = CacheView(data)
    assert node.compute_fn(view) == 2 / 100
