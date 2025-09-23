import math

import pytest

from qmtl.runtime.transforms.microstructure import gap_depth_weighted_sum_node
from qmtl.runtime.sdk.node import SourceNode
from qmtl.runtime.sdk.cache_view import CacheView


def test_gap_depth_weighted_sum_normal_calculation():
    bid_p = SourceNode(interval="1s", period=1, config={"id": "bp"})
    ask_p = SourceNode(interval="1s", period=1, config={"id": "ap"})
    bid_v = SourceNode(interval="1s", period=1, config={"id": "bv"})
    ask_v = SourceNode(interval="1s", period=1, config={"id": "av"})
    node = gap_depth_weighted_sum_node(bid_p, ask_p, bid_v, ask_v)
    data = {
        bid_p.node_id: {1: [(0, [100, 99])]},
        ask_p.node_id: {1: [(0, [101, 102])]},
        bid_v.node_id: {1: [(0, [1, 1])]},
        ask_v.node_id: {1: [(0, [2, 2])]},
    }
    view = CacheView(data)
    expected = ((101 - 100) * (1 + 2) + (102 - 99) * (1 + 2)) / ((1 + 2) + (1 + 2))
    assert node.compute_fn(view) == pytest.approx(expected)


def test_gap_depth_weighted_sum_nan_values():
    bid_p = SourceNode(interval="1s", period=1, config={"id": "bp"})
    ask_p = SourceNode(interval="1s", period=1, config={"id": "ap"})
    bid_v = SourceNode(interval="1s", period=1, config={"id": "bv"})
    ask_v = SourceNode(interval="1s", period=1, config={"id": "av"})
    node = gap_depth_weighted_sum_node(bid_p, ask_p, bid_v, ask_v)
    data = {
        bid_p.node_id: {1: [(0, [100])]},
        ask_p.node_id: {1: [(0, [math.nan])]},
        bid_v.node_id: {1: [(0, [1])]},
        ask_v.node_id: {1: [(0, [2])]},
    }
    view = CacheView(data)
    assert node.compute_fn(view) is None


def test_gap_depth_weighted_sum_invalid_input_type():
    bid_p = SourceNode(interval="1s", period=1, config={"id": "bp"})
    ask_p = SourceNode(interval="1s", period=1, config={"id": "ap"})
    bid_v = SourceNode(interval="1s", period=1, config={"id": "bv"})
    ask_v = SourceNode(interval="1s", period=1, config={"id": "av"})
    node = gap_depth_weighted_sum_node(bid_p, ask_p, bid_v, ask_v)
    data = {
        bid_p.node_id: {1: [(0, 100)]},
        ask_p.node_id: {1: [(0, [101])]},
        bid_v.node_id: {1: [(0, [1])]},
        ask_v.node_id: {1: [(0, [2])]},
    }
    view = CacheView(data)
    assert node.compute_fn(view) is None
