import math
import importlib.util
from types import ModuleType
import sys


def _load_portfolio_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "qmtl.sdk.portfolio", "qmtl/sdk/portfolio.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # type: ignore[index]
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module  # type: ignore[return-value]


pf = _load_portfolio_module()

# Import example function directly (this import touches only the example module)
from qmtl.examples.strategies.rebalance_strategy import compute_rebalance_quantity


def test_compute_rebalance_quantity_progresses_toward_target():
    p = pf.Portfolio(cash=1_000.0)

    # Target 25% weight at $50 -> $250 notional => 5 shares
    qty = compute_rebalance_quantity(p, "AAPL", target_weight=0.25, price=50.0)
    assert math.isclose(qty, 5.0)
    p.apply_fill("AAPL", quantity=qty, price=50.0)

    # Now target 50% weight at new price $60
    # Portfolio value: cash 1_000 - 250 = 750 + market 5 * 60 = 300 => 1,050
    # Desired value 50% * 1,050 = 525; current value 5 * 60 = 300; delta = 225 -> 3.75 shares
    qty2 = compute_rebalance_quantity(p, "AAPL", target_weight=0.5, price=60.0)
    assert math.isclose(qty2, 225.0 / 60.0)
