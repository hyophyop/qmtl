"""Example rebalancing helper built on the portfolio API.

This file demonstrates sizing an order to reach a target portfolio
weight for a symbol using the SDK's portfolio utilities.
"""
from __future__ import annotations

# Prefer the public SDK import, but allow running without full dependencies
try:
    from qmtl.sdk import portfolio as pf  # type: ignore
except Exception:  # pragma: no cover - fallback for lean test environments
    import importlib.util, sys

    spec = importlib.util.spec_from_file_location(
        "qmtl.sdk.portfolio", "qmtl/sdk/portfolio.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # type: ignore[index]
    spec.loader.exec_module(module)  # type: ignore[assignment]
    pf = module  # type: ignore[assignment]


def compute_rebalance_quantity(
    portfolio: pf.Portfolio, symbol: str, target_weight: float, price: float
) -> float:
    """Return quantity required to reach ``target_weight`` for ``symbol``.

    Parameters
    ----------
    portfolio: pf.Portfolio
        Current portfolio snapshot.
    symbol: str
        Trading symbol.
    target_weight: float
        Desired portfolio weight in [0, 1]. Negative values imply short weight.
    price: float
        Current execution price used for sizing.
    """
    # Ensure the portfolio reflects the latest price before sizing the order
    pos = portfolio.get_position(symbol)
    if pos is not None:
        pos.market_price = price
    return pf.order_target_percent(portfolio, symbol, target_weight, price)


__all__ = ["compute_rebalance_quantity"]
