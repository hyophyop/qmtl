import pytest

from qmtl.runtime.indicators import order_book_obi, order_book_obi_ema
from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.node import SourceNode


def _view_for_snapshots(source: SourceNode, snapshots):
    data = {
        source.node_id: {
            source.interval: [(idx, snapshot) for idx, snapshot in enumerate(snapshots)]
        }
    }
    return CacheView(data)


def test_order_book_obi_levels_variation():
    source = SourceNode(interval="1s", period=5)
    snapshot = {
        "bids": [(101, 10), (100, 1), (99, 1)],
        "asks": [(102, 2), (103, 12), (104, 12)],
    }
    view = _view_for_snapshots(source, [snapshot])

    node_lvl1 = order_book_obi(source, levels=1)
    node_lvl3 = order_book_obi(source, levels=3)

    epsilon = 1e-9
    expected_lvl1 = (10 - 2) / (10 + 2 + epsilon)
    expected_lvl3 = (12 - 26) / (12 + 26 + epsilon)

    assert node_lvl1.compute_fn(view) == pytest.approx(expected_lvl1)
    assert node_lvl3.compute_fn(view) == pytest.approx(expected_lvl3)


def test_order_book_obi_accepts_scalar_levels():
    source = SourceNode(interval="1s", period=5)
    snapshot = {"bids": [5, 3, 1], "asks": [5, 3, 1]}
    view = _view_for_snapshots(source, [snapshot])
    node = order_book_obi(source, levels=2)
    assert node.compute_fn(view) == pytest.approx(0.0)


def test_order_book_obi_handles_empty_and_missing_snapshots():
    source = SourceNode(interval="1s", period=5)
    node = order_book_obi(source)

    empty_snapshot = {"bids": [], "asks": []}
    view_with_empty = _view_for_snapshots(source, [empty_snapshot])
    assert node.compute_fn(view_with_empty) == 0.0

    empty_history = _view_for_snapshots(source, [])
    assert node.compute_fn(empty_history) is None


def test_order_book_obi_ema_matches_manual_computation():
    source = SourceNode(interval="1s", period=10)
    ema_period = 3
    ema_node = order_book_obi_ema(source, levels=2, ema_period=ema_period)
    obi_node = ema_node.inputs[0]

    snapshots = [
        {"bids": [(101, 8), (100, 2)], "asks": [(102, 4), (103, 1)]},
        {"bids": [(101, 6), (100, 1)], "asks": [(102, 5), (103, 2)]},
        {"bids": [(101, 7), (100, 3)], "asks": [(102, 2), (103, 2)]},
        {"bids": [(101, 5), (100, 2)], "asks": [(102, 6), (103, 1)]},
    ]

    history: list[tuple[int, dict]] = []
    obi_values: list[float] = []
    for idx, snapshot in enumerate(snapshots):
        history.append((idx, snapshot))
        view = CacheView({source.node_id: {source.interval: list(history)}})
        value = obi_node.compute_fn(view)
        assert value is not None
        obi_values.append(value)

    base_cache = {
        obi_node.node_id: {
            obi_node.interval: [(idx, value) for idx, value in enumerate(obi_values)]
        }
    }
    ema_view = CacheView(base_cache)
    result = ema_node.compute_fn(ema_view)

    tail = obi_values[-ema_period:]
    alpha = 2 / (ema_period + 1)
    expected = tail[0]
    for value in tail[1:]:
        expected = alpha * value + (1 - alpha) * expected

    assert result == pytest.approx(expected)
