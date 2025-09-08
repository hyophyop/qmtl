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
    pf = _load_module("qmtl/sdk/portfolio.py", "qmtl.sdk.portfolio")
    reb = _load_module(
        "qmtl/examples/strategies/rebalance_strategy.py",
        "qmtl.examples.strategies.rebalance_strategy",
    )

    p = pf.Portfolio(cash=1_000.0)
    qty = reb.compute_rebalance_quantity(p, "AAPL", target_weight=0.25, price=50.0)
    assert math.isclose(qty, 5.0)

