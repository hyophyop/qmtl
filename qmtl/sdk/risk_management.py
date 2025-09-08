"""Risk management controls for enhanced backtest accuracy."""

from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional, Tuple, Sequence
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


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
        ratio = abs(self.current_value) / abs(self.limit_value) if self.limit_value != 0 else float('inf')
        
        if ratio >= 2.0:
            return "critical"
        elif ratio >= 1.5:
            return "high"
        elif ratio >= 1.2:
            return "medium"
        else:
            return "low"


@dataclass
class PositionInfo:
    """Information about a position."""
    
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


def aggregate_portfolios(portfolios: Sequence[Tuple[float, Dict[str, PositionInfo]]]) -> Tuple[float, Dict[str, PositionInfo]]:
    """Aggregate positions across multiple strategies.

    Parameters
    ----------
    portfolios:
        Iterable of ``(portfolio_value, positions)`` tuples for each strategy.

    Returns
    -------
    Tuple[float, Dict[str, PositionInfo]]
        Combined portfolio value and merged positions keyed by symbol.
    """

    total_value = 0.0
    aggregated: Dict[str, PositionInfo] = {}

    for value, positions in portfolios:
        total_value += value
        for symbol, pos in positions.items():
            existing = aggregated.get(symbol)
            if existing:
                existing.quantity += pos.quantity
                existing.market_value += pos.market_value
                existing.unrealized_pnl += pos.unrealized_pnl
            else:
                aggregated[symbol] = PositionInfo(
                    symbol=symbol,
                    quantity=pos.quantity,
                    market_value=pos.market_value,
                    unrealized_pnl=pos.unrealized_pnl,
                    entry_price=pos.entry_price,
                    current_price=pos.current_price,
                )

    return total_value, aggregated


class RiskManager:
    """Risk management system for backtesting."""
    
    def __init__(
        self,
        *,
        max_position_size: Optional[float] = None,
        max_leverage: float = 3.0,
        max_drawdown_pct: float = 0.15,  # 15% max drawdown
        max_concentration_pct: float = 0.20,  # 20% max single position
        max_portfolio_volatility: float = 0.25,  # 25% annualized volatility
        position_size_limit_pct: float = 0.10,  # 10% of portfolio per position
        enable_dynamic_sizing: bool = True,
    ):
        """Initialize risk management system.
        
        Parameters
        ----------
        max_position_size : float, optional
            Maximum absolute position size. If None, uses percentage-based sizing.
        max_leverage : float
            Maximum portfolio leverage ratio.
        max_drawdown_pct : float
            Maximum allowed drawdown as fraction (0.15 = 15%).
        max_concentration_pct : float
            Maximum concentration in single position as fraction.
        max_portfolio_volatility : float
            Maximum allowed portfolio volatility (annualized).
        position_size_limit_pct : float
            Maximum position size as percentage of portfolio.
        enable_dynamic_sizing : bool
            Whether to dynamically adjust position sizes based on risk.
        """
        self.max_position_size = max_position_size
        self.max_leverage = max_leverage
        self.max_drawdown_pct = max_drawdown_pct
        self.max_concentration_pct = max_concentration_pct
        self.max_portfolio_volatility = max_portfolio_volatility
        self.position_size_limit_pct = position_size_limit_pct
        self.enable_dynamic_sizing = enable_dynamic_sizing
        
        # Tracking
        self.violations: List[RiskViolation] = []
        self.portfolio_value_history: List[Tuple[int, float]] = []
        self.peak_portfolio_value = 0.0
    
    def validate_position_size(
        self, 
        symbol: str,
        proposed_quantity: float,
        current_price: float,
        portfolio_value: float,
        current_positions: Dict[str, PositionInfo]
    ) -> Tuple[bool, Optional[RiskViolation], float]:
        """Validate proposed position size against risk limits.
        
        Returns
        -------
        Tuple[bool, Optional[RiskViolation], float]
            (is_valid, violation_if_any, adjusted_quantity)
        """
        proposed_value = abs(proposed_quantity * current_price)
        
        # Check absolute position size limit
        if self.max_position_size and proposed_value > self.max_position_size:
            violation = RiskViolation(
                violation_type=RiskViolationType.POSITION_SIZE_LIMIT,
                current_value=proposed_value,
                limit_value=self.max_position_size,
                description=f"Position size {proposed_value:.2f} exceeds absolute limit {self.max_position_size:.2f}",
                timestamp=0,  # Will be set by caller
                symbol=symbol
            )
            
            if self.enable_dynamic_sizing:
                # Adjust to maximum allowed
                adjusted_quantity = (self.max_position_size / current_price) * (1 if proposed_quantity > 0 else -1)
                return False, violation, adjusted_quantity
            else:
                return False, violation, 0.0
        
        # Check percentage-based position size limit
        if portfolio_value > 0:
            position_pct = proposed_value / portfolio_value
            
            if position_pct > self.position_size_limit_pct:
                violation = RiskViolation(
                    violation_type=RiskViolationType.POSITION_SIZE_LIMIT,
                    current_value=position_pct,
                    limit_value=self.position_size_limit_pct,
                    description=f"Position size {position_pct:.1%} exceeds limit {self.position_size_limit_pct:.1%}",
                    timestamp=0,
                    symbol=symbol
                )
                
                if self.enable_dynamic_sizing:
                    # Adjust to maximum allowed percentage
                    max_value = portfolio_value * self.position_size_limit_pct
                    adjusted_quantity = (max_value / current_price) * (1 if proposed_quantity > 0 else -1)
                    return False, violation, adjusted_quantity
                else:
                    return False, violation, 0.0
        
        return True, None, proposed_quantity

    def validate_portfolio_risk(
        self,
        positions: Dict[str, PositionInfo],
        portfolio_value: float,
        timestamp: int
    ) -> List[RiskViolation]:
        """Validate overall portfolio risk metrics."""
        violations = []
        
        if portfolio_value <= 0:
            return violations
        
        # Calculate total exposure and leverage
        total_exposure = sum(pos.exposure for pos in positions.values())
        leverage = total_exposure / portfolio_value if portfolio_value > 0 else 0
        
        # Check leverage limit
        if leverage > self.max_leverage:
            violations.append(RiskViolation(
                violation_type=RiskViolationType.LEVERAGE_LIMIT,
                current_value=leverage,
                limit_value=self.max_leverage,
                description=f"Portfolio leverage {leverage:.2f}x exceeds limit {self.max_leverage:.2f}x",
                timestamp=timestamp
            ))
        
        # Check concentration limits
        for symbol, position in positions.items():
            concentration = position.exposure / portfolio_value
            if concentration > self.max_concentration_pct:
                violations.append(RiskViolation(
                    violation_type=RiskViolationType.CONCENTRATION_LIMIT,
                    current_value=concentration,
                    limit_value=self.max_concentration_pct,
                    description=f"Position concentration in {symbol} is {concentration:.1%}, exceeds limit {self.max_concentration_pct:.1%}",
                    timestamp=timestamp,
                    symbol=symbol
                ))
        
        # Check drawdown limit
        self.peak_portfolio_value = max(self.peak_portfolio_value, portfolio_value)
        if self.peak_portfolio_value > 0:
            current_drawdown = (self.peak_portfolio_value - portfolio_value) / self.peak_portfolio_value
            
            if current_drawdown > self.max_drawdown_pct:
                violations.append(RiskViolation(
                    violation_type=RiskViolationType.DRAWDOWN_LIMIT,
                    current_value=current_drawdown,
                    limit_value=self.max_drawdown_pct,
                    description=f"Portfolio drawdown {current_drawdown:.1%} exceeds limit {self.max_drawdown_pct:.1%}",
                    timestamp=timestamp
                ))
        
        # Track portfolio value for volatility calculation
        self.portfolio_value_history.append((timestamp, portfolio_value))
        
        # Check volatility limit (if we have enough history)
        if len(self.portfolio_value_history) >= 30:  # At least 30 observations
            violations.extend(self._check_volatility_limit(timestamp))
        
        # Store violations
        self.violations.extend(violations)
        
        return violations

    def validate_world_risk(
        self,
        strategies: Sequence[Tuple[float, Dict[str, PositionInfo]]],
        timestamp: int,
    ) -> List[RiskViolation]:
        """Validate risk metrics across multiple strategies.

        Parameters
        ----------
        strategies:
            Iterable of ``(portfolio_value, positions)`` for each strategy in the world.
        timestamp:
            Timestamp for the risk evaluation.
        """

        total_value, aggregated = aggregate_portfolios(strategies)
        return self.validate_portfolio_risk(aggregated, total_value, timestamp)
    
    def _check_volatility_limit(self, timestamp: int) -> List[RiskViolation]:
        """Check portfolio volatility against limits."""
        violations = []
        
        if len(self.portfolio_value_history) < 2:
            return violations
        
        # Calculate returns from recent history (last 30 periods)
        recent_history = self.portfolio_value_history[-30:]
        returns = []
        
        for i in range(1, len(recent_history)):
            prev_value = recent_history[i-1][1]
            curr_value = recent_history[i][1]
            if prev_value > 0:
                ret = (curr_value - prev_value) / prev_value
                returns.append(ret)
        
        if len(returns) >= 10:  # Need at least 10 return observations
            # Calculate annualized volatility (assuming daily returns)
            mean_return = sum(returns) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
            volatility = math.sqrt(variance) * math.sqrt(252)  # Annualize assuming 252 trading days
            
            if volatility > self.max_portfolio_volatility:
                violations.append(RiskViolation(
                    violation_type=RiskViolationType.VOLATILITY_LIMIT,
                    current_value=volatility,
                    limit_value=self.max_portfolio_volatility,
                    description=f"Portfolio volatility {volatility:.1%} exceeds limit {self.max_portfolio_volatility:.1%}",
                    timestamp=timestamp
                ))
        
        return violations
    
    def calculate_position_size(
        self,
        symbol: str,
        target_allocation_pct: float,
        current_price: float,
        portfolio_value: float,
        current_volatility: Optional[float] = None
    ) -> float:
        """Calculate appropriate position size considering risk constraints.
        
        Parameters
        ----------
        symbol : str
            Symbol to size position for.
        target_allocation_pct : float
            Target allocation as percentage (0.1 = 10%).
        current_price : float
            Current price of the asset.
        portfolio_value : float
            Current portfolio value.
        current_volatility : float, optional
            Current asset volatility for risk adjustment.
            
        Returns
        -------
        float
            Recommended position size (number of shares/units).
        """
        if portfolio_value <= 0 or current_price <= 0:
            return 0.0
        
        # Base allocation
        base_allocation = min(target_allocation_pct, self.position_size_limit_pct)
        
        # Adjust for volatility if provided
        if current_volatility and current_volatility > 0:
            # Scale down position size for higher volatility assets
            volatility_adjustment = min(1.0, 0.20 / current_volatility)  # Target 20% volatility
            adjusted_allocation = base_allocation * volatility_adjustment
        else:
            adjusted_allocation = base_allocation
        
        # Calculate position size
        target_value = portfolio_value * adjusted_allocation
        position_size = target_value / current_price
        
        return position_size
    
    def get_risk_summary(self) -> Dict[str, any]:
        """Get summary of risk metrics and violations."""
        return {
            "total_violations": len(self.violations),
            "violation_types": {vtype.value: len([v for v in self.violations if v.violation_type == vtype]) 
                             for vtype in RiskViolationType},
            "critical_violations": len([v for v in self.violations if v.severity == "critical"]),
            "high_violations": len([v for v in self.violations if v.severity == "high"]),
            "peak_portfolio_value": self.peak_portfolio_value,
            "current_drawdown": self._calculate_current_drawdown(),
            "risk_config": {
                "max_leverage": self.max_leverage,
                "max_drawdown_pct": self.max_drawdown_pct,
                "max_concentration_pct": self.max_concentration_pct,
                "position_size_limit_pct": self.position_size_limit_pct,
            }
        }
    
    def _calculate_current_drawdown(self) -> float:
        """Calculate current portfolio drawdown."""
        if not self.portfolio_value_history or self.peak_portfolio_value <= 0:
            return 0.0

        current_value = self.portfolio_value_history[-1][1]
        return (self.peak_portfolio_value - current_value) / self.peak_portfolio_value


__all__ = [
    "PortfolioScope",
    "RiskViolationType",
    "RiskViolation",
    "PositionInfo",
    "aggregate_portfolios",
    "RiskManager",
]
