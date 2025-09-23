from qmtl.runtime.transforms import (
    volume_stats,
    order_book_imbalance,
    execution_imbalance,
    rate_of_change_series,
    price_delta,
)
from qmtl.runtime.indicators import volatility


def test_volume_stats():
    mean, std = volume_stats([1, 2, 3])
    assert round(mean, 2) == 2.0
    assert round(std, 2) == 0.82


def test_order_book_imbalance():
    assert order_book_imbalance(60, 40) == 0.2


def test_execution_imbalance():
    assert execution_imbalance(30, 10) == 0.5


def test_rate_of_change_series():
    assert rate_of_change_series([1, 2]) == 1.0


def test_price_delta():
    assert price_delta(10, 12) == 2


def test_volatility():
    # prices produce returns [0.1, -0.05]
    assert round(volatility([1.0, 1.1, 1.045]), 4) == 0.1061
