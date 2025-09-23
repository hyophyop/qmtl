"""Data models supporting risk evaluation logic."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PortfolioScope(str, Enum):
    """Scope for portfolio risk calculations."""

    STRATEGY = "strategy"
    WORLD = "world"


class RiskViolationType(str, Enum):
    """Types of risk violations."""

    POSITION_SIZE_LIMIT = "position_size_limit"
    LEVERAGE_LIMIT = "leverage_limit"
    DRAWDOWN_LIMIT = "drawdown_limit"
    CONCENTRATION_LIMIT = "concentration_limit"
    VOLATILITY_LIMIT = "volatility_limit"


@dataclass
class RiskViolation:
    """Represents a risk management violation."""

    violation_type: RiskViolationType
    current_value: float
    limit_value: float
    description: str
    timestamp: int
    symbol: Optional[str] = None

    @property
    def severity(self) -> str:
        """Calculate severity based on how much the limit is exceeded."""

        ratio = (
            abs(self.current_value) / abs(self.limit_value)
            if self.limit_value not in (0, 0.0)
            else float("inf")
        )

        if ratio >= 2.0:
            return "critical"
        if ratio >= 1.5:
            return "high"
        if ratio >= 1.2:
            return "medium"
        return "low"


@dataclass
class PositionInfo:
    """Information about a portfolio position."""

    symbol: str
    quantity: float
    market_value: float
    unrealized_pnl: float
    entry_price: float
    current_price: float

    @property
    def exposure(self) -> float:
        """Absolute market value exposure."""

        return abs(self.market_value)


@dataclass
class RiskConfig:
    """Configuration for portfolio risk thresholds."""

    max_position_size: Optional[float] = None
    max_leverage: float = 3.0
    max_drawdown_pct: float = 0.15
    max_concentration_pct: float = 0.20
    max_portfolio_volatility: float = 0.25
    position_size_limit_pct: float = 0.10
    enable_dynamic_sizing: bool = True
    volatility_lookback: int = 30
    volatility_min_samples: int = 10


__all__ = [
    "PortfolioScope",
    "RiskViolationType",
    "RiskViolation",
    "PositionInfo",
    "RiskConfig",
]
