import math

import pytest

from qmtl.runtime.sdk.execution_modeling import OrderSide, OrderType


@pytest.mark.parametrize(
    "trade_value, expected",
    [
        pytest.param(10000, 10.0, id="rate-applies"),
        pytest.param(100, 1.0, id="minimum-applies"),
    ],
)
def test_calculate_commission(execution_model, trade_value, expected):
    assert execution_model.calculate_commission(trade_value) == expected


@pytest.mark.parametrize(
    "side, expected_sign",
    [
        pytest.param(OrderSide.BUY, 1.0, id="market-buy"),
        pytest.param(OrderSide.SELL, -1.0, id="market-sell"),
    ],
)
def test_market_order_slippage_sign(execution_model, liquid_market_data, side, expected_sign):
    slippage = execution_model.calculate_slippage(
        liquid_market_data,
        OrderType.MARKET,
        side,
        quantity=100,
    )

    assert math.copysign(1.0, slippage) == expected_sign


def test_limit_orders_reduce_slippage(execution_model, liquid_market_data):
    market_slippage = abs(
        execution_model.calculate_slippage(
            liquid_market_data, OrderType.MARKET, OrderSide.BUY, quantity=100
        )
    )
    limit_slippage = abs(
        execution_model.calculate_slippage(
            liquid_market_data, OrderType.LIMIT, OrderSide.BUY, quantity=100
        )
    )

    assert limit_slippage < market_slippage


def test_market_impact_scales_with_size(execution_model, liquid_market_data):
    small_order = execution_model.calculate_slippage(
        liquid_market_data, OrderType.MARKET, OrderSide.BUY, quantity=100
    )
    large_order = execution_model.calculate_slippage(
        liquid_market_data, OrderType.MARKET, OrderSide.BUY, quantity=1000
    )

    assert large_order > small_order


def test_commission_and_slippage_values(low_cost_execution_model, quiet_market_data):
    slippage = low_cost_execution_model.calculate_slippage(
        quiet_market_data, OrderType.MARKET, OrderSide.BUY, quantity=100
    )
    expected_slippage = (
        quiet_market_data.mid_price * 0.0001 + quiet_market_data.spread / 2.0
    )
    assert slippage == pytest.approx(expected_slippage)

    fill = low_cost_execution_model.simulate_execution(
        order_id="t1",
        symbol="XYZ",
        side=OrderSide.BUY,
        quantity=100,
        order_type=OrderType.MARKET,
        requested_price=100.0,
        market_data=quiet_market_data,
        timestamp=0,
    )
    expected_price = quiet_market_data.ask + expected_slippage
    expected_commission = expected_price * 100 * 0.001

    assert fill.fill_price == pytest.approx(expected_price)
    assert fill.commission == pytest.approx(expected_commission)
