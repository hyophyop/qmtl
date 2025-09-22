from qmtl.sdk.execution_modeling import OrderSide, OrderType


def test_simulate_market_order(execution_model, liquid_market_data):
    fill = execution_model.simulate_execution(
        order_id="mkt-001",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=100,
        order_type=OrderType.MARKET,
        requested_price=100.0,
        market_data=liquid_market_data,
        timestamp=1000,
    )

    assert fill.order_id == "mkt-001"
    assert fill.side is OrderSide.BUY
    assert fill.quantity == 100
    assert fill.fill_time == 1100  # timestamp + latency
    assert fill.fill_price > liquid_market_data.ask
    assert fill.slippage > 0
    assert fill.commission >= 1.0


def test_simulate_limit_order(execution_model, liquid_market_data):
    fill = execution_model.simulate_execution(
        order_id="lmt-001",
        symbol="AAPL",
        side=OrderSide.SELL,
        quantity=100,
        order_type=OrderType.LIMIT,
        requested_price=99.0,
        market_data=liquid_market_data,
        timestamp=1000,
    )

    assert fill.side is OrderSide.SELL
    assert fill.fill_price < liquid_market_data.bid
    assert fill.slippage < 0
    assert abs(fill.fill_price - 99.0) < abs(liquid_market_data.bid - 99.0)
