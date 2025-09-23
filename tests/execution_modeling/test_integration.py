from qmtl.runtime.sdk.execution_modeling import (
    ExecutionModel,
    OrderSide,
    OrderType,
    create_market_data_from_ohlcv,
)
from qmtl.runtime.transforms.alpha_performance import calculate_execution_metrics


def test_integration_execution_workflow():
    model = ExecutionModel(
        commission_rate=0.0005,
        commission_minimum=1.0,
        base_slippage_bps=1.5,
        market_impact_coeff=0.05,
    )
    market_data = create_market_data_from_ohlcv(
        timestamp=1000,
        open_price=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=50000,
    )

    is_valid, _ = model.validate_order(OrderSide.BUY, 1000, 100.5, market_data)
    assert is_valid

    fill = model.simulate_execution(
        order_id="integration_001",
        symbol="TEST",
        side=OrderSide.BUY,
        quantity=1000,
        order_type=OrderType.MARKET,
        requested_price=100.0,
        market_data=market_data,
        timestamp=1000,
    )

    assert fill.quantity == 1000
    assert fill.fill_price > market_data.ask
    assert fill.total_cost > 0

    metrics = calculate_execution_metrics([fill])
    assert metrics["total_trades"] == 1
    assert metrics["total_commission"] >= 1.0
