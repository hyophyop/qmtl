import math
from pathlib import Path

from qmtl.runtime.plugin_loader import load_portfolio_module


pf = load_portfolio_module(
    module_file=Path(__file__).resolve().parents[2] / "runtime" / "sdk" / "portfolio.py"
)

# Import example function directly (this import touches only the example module)
from qmtl.examples.strategies.rebalance_strategy import compute_rebalance_quantity


def test_compute_rebalance_quantity_progresses_toward_target():
    p = pf.Portfolio(cash=1_000.0)

    # Target 25% weight at $50 -> $250 notional => 5 shares
    qty = compute_rebalance_quantity(p, "AAPL", target_weight=0.25, price=50.0)
    assert math.isclose(qty, 5.0)
    p.apply_fill("AAPL", quantity=qty, price=50.0)

    # Update market price for subsequent sizing
    p.positions["AAPL"].market_price = 60.0

    # Now target 50% weight at new price $60
    # Portfolio value: cash 1_000 - 250 = 750 + market 5 * 60 = 300 => 1,050
    # Desired value 50% * 1,050 = 525; current value 5 * 60 = 300; delta = 225 -> 3.75 shares
    qty2 = compute_rebalance_quantity(p, "AAPL", target_weight=0.5, price=60.0)
    assert math.isclose(qty2, 225.0 / 60.0)
