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

    Notes on mark-to-market:
    - ``Portfolio.total_value`` aggregates each position's ``market_price``.
    - When sizing at a new price (e.g., after a price move), ensure the
      portfolio value reflects that price, otherwise target weights can be
      mis-estimated. This helper computes using a mark-to-market adjustment
      for ``symbol`` at the provided ``price`` without mutating the portfolio.

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
    current = portfolio.get_position(symbol)
    # Mark the position to the provided price for the calculations below.
    current_value = current.quantity * price if current else 0.0
    total_value = portfolio.cash + sum(
        (p.quantity * price if p.symbol == symbol else p.market_value)
        for p in portfolio.positions.values()
    )
    desired_value = total_value * target_weight
    delta_value = desired_value - current_value
    return pf.order_value(symbol, delta_value, price)


__all__ = ["compute_rebalance_quantity"]
