import pytest

from qmtl.sdk.portfolio import (
    Portfolio,
    Position,
    order_percent,
    order_target_percent,
    order_value,
)


def test_position_properties_and_orders():
    portfolio = Portfolio(cash=10000)
    # buy 50 shares at 100
    portfolio.apply_fill("AAPL", 50, 100)
    pos = portfolio.get_position("AAPL")
    assert pos is not None
    assert pos.quantity == 50
    assert pos.avg_cost == 100
    assert portfolio.cash == 10000 - 5000
    assert pos.market_value == 5000
    assert pos.unrealized_pnl == 0

    # order helpers
    assert order_value("AAPL", 1000, 100) == 10

    qty_percent = order_percent(portfolio, "AAPL", 0.1, 100)
    expected_percent_qty = portfolio.total_value * 0.1 / 100
    assert qty_percent == pytest.approx(expected_percent_qty)

    qty_target = order_target_percent(portfolio, "AAPL", 0.5, 100)
    desired_value = portfolio.total_value * 0.5
    current_value = pos.market_value
    assert qty_target == pytest.approx((desired_value - current_value) / 100)

    # sell part of position
    portfolio.apply_fill("AAPL", -20, 110)
    pos = portfolio.get_position("AAPL")
    assert pos is not None
    assert pos.quantity == 30
    assert portfolio.cash == pytest.approx(10000 - 5000 + 2200)
    assert pos.market_price == 110
    assert pos.market_value == 3300
    assert pos.unrealized_pnl == pytest.approx((110 - 100) * 30)
