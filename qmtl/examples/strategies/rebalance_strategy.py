"""Example rebalancing helper built on the portfolio API.

This file demonstrates sizing an order to reach a target portfolio
weight for a symbol using the SDK's portfolio utilities.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Protocol

_PORTFOLIO_FALLBACK = (
    Path(__file__).resolve().parents[2] / "runtime" / "sdk" / "portfolio.py"
)

if TYPE_CHECKING:  # pragma: no cover - typing aid only
    from qmtl.runtime.plugin_loader import PortfolioModule
else:
    # Minimal protocol to avoid importing qmtl in lean environments where optional
    # dependencies are unavailable.
    class PortfolioModule(Protocol):
        Portfolio: type
        Position: type
        order_value: Callable[[str, float, float], float]


def _load_module_from_path(module_name: str, module_file: Path) -> PortfolioModule:
    spec = importlib.util.spec_from_file_location(module_name, module_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module '{module_name}' from {module_file!s}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module  # type: ignore[return-value]


def _load_portfolio_helpers(module_file: Path) -> PortfolioModule:
    """Load the portfolio helpers without importing ``qmtl`` if unavailable."""

    try:
        from qmtl.runtime.plugin_loader import load_portfolio_module
    except ModuleNotFoundError:
        return _load_module_from_path("qmtl.runtime.sdk.portfolio", module_file)

    return load_portfolio_module(module_file=module_file)


pf: PortfolioModule = _load_portfolio_helpers(_PORTFOLIO_FALLBACK)


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
