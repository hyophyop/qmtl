import importlib.util
import math
import types
from pathlib import Path


def _load_module(module_name: str, module_file: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, module_file)
    if spec is None or spec.loader is None:
        msg = f"Could not load module '{module_name}' from {module_file!s}"
        raise ImportError(msg)

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pf = _load_module(
    "qmtl.runtime.sdk.portfolio",
    Path(__file__).resolve().parents[2] / "runtime" / "sdk" / "portfolio.py",
)

rebalance = _load_module(
    "rebalance_strategy",
    Path(__file__).resolve().parent.parent / "strategies" / "rebalance_strategy.py",
)

compute_rebalance_quantity = rebalance.compute_rebalance_quantity


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
