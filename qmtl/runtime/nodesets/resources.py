from __future__ import annotations

"""Shared execution resources for Node Set builders.

This module centralizes the wiring of activation weighting (soft gating)
and world-scoped portfolio storage so every Node Set recipe composes the
same behavior consistently. Recipes and adapters can import the helpers
here instead of re-implementing the logic locally.
"""

from dataclasses import dataclass
from typing import Callable, Mapping

from qmtl.runtime.sdk.portfolio import Portfolio
from .options import PortfolioScope


_WORLD_PORTFOLIOS: dict[str, Portfolio] = {}


@dataclass(frozen=True)
class ExecutionResources:
    """Bundle of shared execution resources for a Node Set."""

    portfolio: Portfolio
    weight_fn: Callable[[Mapping[str, object]], float] | None


def _infer_side(order: Mapping[str, object]) -> str:
    """Infer order side for activation weighting."""

    side = order.get("side")
    if side:
        s = str(side).lower()
        if s in {"buy", "sell", "long", "short"}:
            return "buy" if s in {"buy", "long"} else "sell"
    qty = order.get("quantity")
    if _is_numeric(qty):
        return "buy" if float(qty) >= 0 else "sell"
    return _infer_side_from_value(order)


def _is_numeric(value: object) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _infer_side_from_value(order: Mapping[str, object]) -> str:
    for key in ("value", "percent", "target_percent"):
        val = order.get(key)
        if _is_numeric(val):
            return "buy" if float(val) >= 0 else "sell"
    return "buy"


def make_activation_weight_fn() -> Callable[[Mapping[str, object]], float]:
    """Return a weight function backed by Runner's ActivationManager."""

    def _weight(order: Mapping[str, object]) -> float:
        try:
            from qmtl.runtime.sdk.runner import Runner  # Late import to avoid cycles

            am = Runner.services().activation_manager
            if am is None:
                return 1.0
            side = _infer_side(order)
            weight = float(am.weight_for_side(side))
            if weight < 0.0:
                return 0.0
            if weight > 1.0:
                return 1.0
            return weight
        except Exception:
            return 1.0

    return _weight


def get_portfolio_for_scope(world_id: str, scope: PortfolioScope) -> Portfolio:
    """Return a Portfolio scoped per-world when requested."""

    if scope == "world":
        return _WORLD_PORTFOLIOS.setdefault(world_id, Portfolio())
    return Portfolio()


def get_execution_resources(
    world_id: str,
    *,
    portfolio_scope: PortfolioScope = "strategy",
    activation_weighting: bool = True,
) -> ExecutionResources:
    """Return shared execution resources for a Node Set."""

    portfolio = get_portfolio_for_scope(world_id, portfolio_scope)
    weight_fn = make_activation_weight_fn() if activation_weighting else None
    return ExecutionResources(portfolio=portfolio, weight_fn=weight_fn)


def clear_shared_portfolios() -> None:
    """Reset cached world-scoped portfolio instances (for tests)."""

    _WORLD_PORTFOLIOS.clear()


__all__ = [
    "ExecutionResources",
    "get_execution_resources",
    "get_portfolio_for_scope",
    "make_activation_weight_fn",
    "clear_shared_portfolios",
]
