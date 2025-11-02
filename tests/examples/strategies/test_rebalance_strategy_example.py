import math
import importlib.util
import sys


def _load_module(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # type: ignore[index]
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_rebalance_example_function_works_with_portfolio_helpers():
    # Load portfolio and example modules without importing qmtl package
    pf = _load_module("qmtl/runtime/sdk/portfolio.py", "qmtl.runtime.sdk.portfolio")
    reb = _load_module(
        "qmtl/examples/strategies/rebalance_strategy.py",
        "qmtl.examples.strategies.rebalance_strategy",
    )

    p = pf.Portfolio(cash=1_000.0)

    # Step 1: target 25% at $50 => $250 notional => 5 shares
    qty = reb.compute_rebalance_quantity(p, "AAPL", target_weight=0.25, price=50.0)
    assert math.isclose(qty, 5.0)
    p.apply_fill("AAPL", quantity=qty, price=50.0)

    # Step 2: price moves to $60; rebalance to 50% should mark-to-market
    # Total value: cash 1000 - 250 = 750 + 5 * 60 = 300 => 1050
    # Desired 50% = 525; current value 300; delta 225 -> 3.75 shares
    qty2 = reb.compute_rebalance_quantity(p, "AAPL", target_weight=0.5, price=60.0)
    assert math.isclose(qty2, 225.0 / 60.0)
