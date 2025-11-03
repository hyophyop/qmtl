import pytest

from qmtl.runtime.indicators import microprice_imbalance
from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.node import SourceNode


def _view_for_snapshots(source: SourceNode, snapshots):
    data = {
        source.node_id: {
            source.interval: [(idx, snapshot) for idx, snapshot in enumerate(snapshots)]
        }
    }
    return CacheView(data)


def test_microprice_imbalance_computes_expected_values():
    source = SourceNode(interval="1s", period=5)
    snapshot = {
        "bids": [(100.0, 4.0), (99.5, 3.0), (99.0, 2.0)],
        "asks": [(101.0, 3.0), (101.5, 2.0), (102.0, 1.0)],
    }

    node = microprice_imbalance(source, top_levels=2)
    result = node.compute_fn(_view_for_snapshots(source, [snapshot]))

    assert result is not None

    bid_price, bid_size = snapshot["bids"][0]
    ask_price, ask_size = snapshot["asks"][0]
    epsilon = 1e-9
    expected_microprice = (
        ask_price * bid_size + bid_price * ask_size
    ) / (bid_size + ask_size + epsilon)

    bid_total = snapshot["bids"][0][1] + snapshot["bids"][1][1]
    ask_total = snapshot["asks"][0][1] + snapshot["asks"][1][1]
    expected_imbalance = (bid_total - ask_total) / (bid_total + ask_total + epsilon)

    assert result["microprice"] == pytest.approx(expected_microprice)
    assert result["imbalance"] == pytest.approx(expected_imbalance)


def test_microprice_imbalance_handles_missing_levels():
    source = SourceNode(interval="1s", period=5)
    snapshot = {"bids": [], "asks": [(101.0, 5.0), (101.5, 1.0)]}

    node = microprice_imbalance(source, top_levels=3)
    result = node.compute_fn(_view_for_snapshots(source, [snapshot]))

    assert result is not None
    assert result["microprice"] is None

    epsilon = 1e-9
    ask_total = snapshot["asks"][0][1] + snapshot["asks"][1][1]
    expected_imbalance = (0.0 - ask_total) / (ask_total + epsilon)
    assert result["imbalance"] == pytest.approx(expected_imbalance)


def test_microprice_imbalance_zero_depth_returns_zero_metrics():
    source = SourceNode(interval="1s", period=5)
    snapshot = {"bids": [(100.0, 0.0)], "asks": [(101.0, 0.0)]}

    node = microprice_imbalance(source)
    result = node.compute_fn(_view_for_snapshots(source, [snapshot]))

    assert result is not None
    assert result["microprice"] == pytest.approx(0.0)
    assert result["imbalance"] == pytest.approx(0.0)
