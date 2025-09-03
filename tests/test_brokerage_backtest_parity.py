from __future__ import annotations

import math

from qmtl.sdk.execution_modeling import ExecutionModel, OrderSide, OrderType, create_market_data_from_ohlcv
from qmtl.sdk.brokerage_backtest import BrokerageBacktestEngine, ExecCompatParams, make_brokerage_model_for_compat


def almost_equal(a: float, b: float, tol: float = 1e-9) -> bool:
    return math.isclose(a, b, rel_tol=tol, abs_tol=tol)


def test_parity_market_orders():
    params = ExecCompatParams(
        commission_rate=0.001,
        commission_minimum=1.0,
        base_slippage_bps=2.0,
        market_impact_coeff=0.1,
        latency_ms=100,
    )

    em = ExecutionModel(
        commission_rate=params.commission_rate,
        commission_minimum=params.commission_minimum,
        base_slippage_bps=params.base_slippage_bps,
        market_impact_coeff=params.market_impact_coeff,
        latency_ms=params.latency_ms,
    )
    brokerage = make_brokerage_model_for_compat(params)
    engine = BrokerageBacktestEngine(brokerage, latency_ms=params.latency_ms, compat_params=params)

    md = create_market_data_from_ohlcv(
        timestamp=1_700_000_000,
        open_price=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=10_000,
        spread_estimate=0.001,
    )

    # BUY
    f1 = em.simulate_execution(
        order_id="o1",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=100,
        order_type=OrderType.MARKET,
        requested_price=100.0,
        market_data=md,
        timestamp=1_700_000_000,
    )
    # simulate_execution no longer accepts a compat_mode flag; parity behaviour is default
    f2 = engine.simulate_execution(
        order_id="o1",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=100,
        order_type=OrderType.MARKET,
        requested_price=100.0,
        market_data=md,
        timestamp=1_700_000_000,
    )
    assert almost_equal(f1.fill_price, f2.fill_price)
    assert almost_equal(f1.commission, f2.commission)
    assert almost_equal(f1.slippage, f2.slippage)
    assert f1.fill_time == f2.fill_time

    # SELL
    f1s = em.simulate_execution(
        order_id="o2",
        symbol="AAPL",
        side=OrderSide.SELL,
        quantity=50,
        order_type=OrderType.MARKET,
        requested_price=100.0,
        market_data=md,
        timestamp=1_700_000_000,
    )
    # default parity path without compat_mode flag
    f2s = engine.simulate_execution(
        order_id="o2",
        symbol="AAPL",
        side=OrderSide.SELL,
        quantity=50,
        order_type=OrderType.MARKET,
        requested_price=100.0,
        market_data=md,
        timestamp=1_700_000_000,
    )
    assert almost_equal(f1s.fill_price, f2s.fill_price)
    assert almost_equal(f1s.commission, f2s.commission)
    assert almost_equal(f1s.slippage, f2s.slippage)
    assert f1s.fill_time == f2s.fill_time


def test_parity_limit_orders():
    params = ExecCompatParams()
    em = ExecutionModel(
        commission_rate=params.commission_rate,
        commission_minimum=params.commission_minimum,
        base_slippage_bps=params.base_slippage_bps,
        market_impact_coeff=params.market_impact_coeff,
        latency_ms=params.latency_ms,
    )
    engine = BrokerageBacktestEngine(make_brokerage_model_for_compat(params), latency_ms=params.latency_ms, compat_params=params)

    md = create_market_data_from_ohlcv(
        timestamp=1_700_000_000,
        open_price=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=5_000,
        spread_estimate=0.001,
    )

    f1 = em.simulate_execution(
        order_id="o3",
        symbol="MSFT",
        side=OrderSide.BUY,
        quantity=10,
        order_type=OrderType.LIMIT,
        requested_price=99.5,
        market_data=md,
        timestamp=1_700_000_100,
    )
    # ensure limit order path also uses default parity behaviour
    f2 = engine.simulate_execution(
        order_id="o3",
        symbol="MSFT",
        side=OrderSide.BUY,
        quantity=10,
        order_type=OrderType.LIMIT,
        requested_price=99.5,
        market_data=md,
        timestamp=1_700_000_100,
    )
    assert almost_equal(f1.fill_price, f2.fill_price)
    assert almost_equal(f1.commission, f2.commission)
    assert almost_equal(f1.slippage, f2.slippage)
    assert f1.fill_time == f2.fill_time

