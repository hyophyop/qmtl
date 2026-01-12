from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


TradeMode = Literal["simulate", "paper", "live"]
PortfolioScope = Literal["strategy", "world"]
LabelOrderGuard = Literal["off", "warn", "block"]


@dataclass(frozen=True)
class NodeSetOptions:
    mode: TradeMode = "simulate"
    portfolio_scope: PortfolioScope = "strategy"
    activation_weighting: bool = True
    label_order_guard: LabelOrderGuard = "block"


__all__ = ["LabelOrderGuard", "NodeSetOptions", "TradeMode", "PortfolioScope"]
