from __future__ import annotations

import pytest


def test_ccxt_fee_profile_demo_builds_models_and_applies_fees():
    from qmtl.examples.brokerage_demo.ccxt_fee_profile_demo import (
        build_spot_model,
        build_futures_model,
        run_demo,
    )
    from qmtl.brokerage import BrokerageModel, Order, OrderType, TimeInForce

    # Build models without ccxt (deterministic defaults)
    spot = build_spot_model(detect_fees=False, defaults=(0.001, 0.002))
    fut = build_futures_model(detect_fees=False, defaults=(0.003, 0.004))

    assert isinstance(spot, BrokerageModel)
    assert isinstance(fut, BrokerageModel)

    # Market = taker, Limit = maker
    mkt_order = Order(symbol="BTC/USDT", quantity=1, price=10_000.0, type=OrderType.MARKET, tif=TimeInForce.DAY)
    lmt_order = Order(symbol="BTC/USDT", quantity=1, price=10_000.0, type=OrderType.LIMIT, tif=TimeInForce.GTC, limit_price=9_900.0)

    # Use internal helper from the demo
    from qmtl.examples.brokerage_demo.ccxt_fee_profile_demo import _exec

    res_mkt = _exec(spot, mkt_order, market_price=10_000.0, cash=100_000.0)
    res_lmt = _exec(spot, lmt_order, market_price=9_900.0, cash=100_000.0)

    assert pytest.approx(res_mkt["fill"]["fee"]) == 10_000.0 * 0.002
    assert pytest.approx(res_lmt["fill"]["fee"]) == 9_900.0 * 0.001

    # Smoke test: run_demo returns structured dict
    out = run_demo()
    assert set(out.keys()) >= {"spot", "futures"}

