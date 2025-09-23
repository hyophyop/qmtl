from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


TradeMode = Literal["simulate", "paper", "live"]
PortfolioScope = Literal["strategy", "world"]


@dataclass(frozen=True)
class NodeSetOptions:
    mode: TradeMode = "simulate"
    portfolio_scope: PortfolioScope = "strategy"
    activation_weighting: bool = True


__all__ = ["NodeSetOptions", "TradeMode", "PortfolioScope"]

