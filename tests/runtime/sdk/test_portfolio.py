import math
import importlib.util
from types import ModuleType
import sys


def _load_portfolio_module() -> ModuleType:
    """Load qmtl.runtime.sdk.portfolio without importing qmtl.runtime.sdk.__init__."""
    spec = importlib.util.spec_from_file_location(
        "qmtl.runtime.sdk.portfolio", "qmtl/runtime/sdk/portfolio.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # type: ignore[index]
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module  # type: ignore[return-value]


pf = _load_portfolio_module()


def test_apply_fill_buy_updates_position_and_cash():
    p = pf.Portfolio(cash=10_000.0)
    # Buy 10 shares at $100 with $1 commission
    p.apply_fill("AAPL", quantity=10, price=100.0, commission=1.0)

    pos = p.get_position("AAPL")
    assert pos is not None
    assert pos.symbol == "AAPL"
    assert pos.quantity == 10
    assert pos.avg_cost == 100.0
    assert pos.market_price == 100.0

    # Cash reduced by notional + commission
    assert math.isclose(p.cash, 10_000.0 - (10 * 100.0) - 1.0, rel_tol=1e-9)
    # Total value equals cash + market value
    assert math.isclose(p.total_value, p.cash + pos.market_value, rel_tol=1e-9)


def test_apply_fill_sell_reduces_position_and_handles_close():
    p = pf.Portfolio(cash=0.0)
    p.apply_fill("AAPL", quantity=10, price=100.0)

    # Sell 4 shares at $110
    p.apply_fill("AAPL", quantity=-4, price=110.0)
    pos = p.get_position("AAPL")
    assert pos is not None
    assert pos.quantity == 6
    # Avg cost unchanged on sell
    assert pos.avg_cost == 100.0
    # Cash increased by proceeds
    assert math.isclose(p.cash, -(10 * 100.0) + (4 * 110.0), rel_tol=1e-9)

    # Close remaining position
    p.apply_fill("AAPL", quantity=-6, price=105.0)
    assert p.get_position("AAPL") is None


def test_order_helpers_value_percent_and_target_percent():
    p = pf.Portfolio(cash=1_000.0)

    # With no positions, order_percent == order_target_percent
    qty1 = pf.order_percent(p, "AAPL", percent=0.1, price=50.0)
    qty2 = pf.order_target_percent(p, "AAPL", percent=0.1, price=50.0)
    assert math.isclose(qty1, qty2)
    # 10% of $1000 is $100 -> 2 shares at $50
    assert math.isclose(qty1, 2.0)

    # After buying 2 @ $50, update market price to $60 and target 20%
    p.apply_fill("AAPL", quantity=2, price=50.0)
    p.positions["AAPL"].market_price = 60.0
    # Portfolio value: cash $900 + market $120 = $1,020
    qty3 = pf.order_target_percent(p, "AAPL", percent=0.2, price=60.0)
    # Desired value 20% of 1,020 = 204; current value 2 * 60 = 120; delta = 84 -> 1.4 shares
    assert math.isclose(qty3, 84.0 / 60.0)

    # order_value guard
    try:
        pf.order_value("AAPL", value=100.0, price=0.0)
        assert False, "Expected ValueError for zero price"
    except ValueError:
        pass
