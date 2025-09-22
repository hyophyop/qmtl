"""Composable risk evaluation controls."""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Tuple

from .models import PositionInfo, RiskViolation, RiskViolationType


def evaluate_position_size(
    symbol: str,
    proposed_quantity: float,
    current_price: float,
    portfolio_value: float,
    current_positions: Dict[str, PositionInfo],
    *,
    max_position_size: Optional[float],
    position_size_limit_pct: float,
    enable_dynamic_sizing: bool,
) -> Tuple[bool, Optional[RiskViolation], float]:
    """Validate a proposed position against absolute and percentage limits."""

    proposed_value = abs(proposed_quantity * current_price)

    if max_position_size and proposed_value > max_position_size:
        violation = RiskViolation(
            violation_type=RiskViolationType.POSITION_SIZE_LIMIT,
            current_value=proposed_value,
            limit_value=max_position_size,
            description=(
                f"Position size {proposed_value:.2f} exceeds absolute limit {max_position_size:.2f}"
            ),
            timestamp=0,
            symbol=symbol,
        )

        if enable_dynamic_sizing:
            adjusted_quantity = (max_position_size / current_price) * (
                1 if proposed_quantity > 0 else -1
            )
            return False, violation, adjusted_quantity

        return False, violation, 0.0

    if portfolio_value > 0:
        position_pct = proposed_value / portfolio_value
        if position_pct > position_size_limit_pct:
            violation = RiskViolation(
                violation_type=RiskViolationType.POSITION_SIZE_LIMIT,
                current_value=position_pct,
                limit_value=position_size_limit_pct,
                description=(
                    "Position size {pct:.1%} exceeds limit {limit:.1%}".format(
                        pct=position_pct, limit=position_size_limit_pct
                    )
                ),
                timestamp=0,
                symbol=symbol,
            )

            if enable_dynamic_sizing:
                max_value = portfolio_value * position_size_limit_pct
                adjusted_quantity = (max_value / current_price) * (
                    1 if proposed_quantity > 0 else -1
                )
                return False, violation, adjusted_quantity

            return False, violation, 0.0

    return True, None, proposed_quantity


def evaluate_leverage(
    total_exposure: float,
    portfolio_value: float,
    *,
    max_leverage: float,
    timestamp: int,
) -> Optional[RiskViolation]:
    """Validate leverage against configured limits."""

    if portfolio_value <= 0:
        return None

    leverage = total_exposure / portfolio_value
    if leverage > max_leverage:
        return RiskViolation(
            violation_type=RiskViolationType.LEVERAGE_LIMIT,
            current_value=leverage,
            limit_value=max_leverage,
            description=(
                f"Portfolio leverage {leverage:.2f}x exceeds limit {max_leverage:.2f}x"
            ),
            timestamp=timestamp,
        )

    return None


def evaluate_concentration(
    positions: Dict[str, PositionInfo],
    portfolio_value: float,
    *,
    max_concentration_pct: float,
    timestamp: int,
) -> List[RiskViolation]:
    """Validate single-position concentration."""

    if portfolio_value <= 0:
        return []

    violations: List[RiskViolation] = []
    for symbol, position in positions.items():
        concentration = position.exposure / portfolio_value
        if concentration > max_concentration_pct:
            violations.append(
                RiskViolation(
                    violation_type=RiskViolationType.CONCENTRATION_LIMIT,
                    current_value=concentration,
                    limit_value=max_concentration_pct,
                    description=(
                        "Position concentration in {symbol} is {concentration:.1%}, exceeds limit {limit:.1%}".format(
                            symbol=symbol,
                            concentration=concentration,
                            limit=max_concentration_pct,
                        )
                    ),
                    timestamp=timestamp,
                    symbol=symbol,
                )
            )

    return violations


class DrawdownControl:
    """Track peak portfolio value and detect drawdown breaches."""

    def __init__(self, max_drawdown_pct: float) -> None:
        self.max_drawdown_pct = max_drawdown_pct
        self.peak_portfolio_value = 0.0
        self.current_drawdown = 0.0

    def update(self, portfolio_value: float, timestamp: int) -> List[RiskViolation]:
        """Update drawdown state and emit violations when breached."""

        if portfolio_value <= 0:
            self.current_drawdown = 0.0
            return []

        self.peak_portfolio_value = max(self.peak_portfolio_value, portfolio_value)
        if self.peak_portfolio_value <= 0:
            self.current_drawdown = 0.0
            return []

        self.current_drawdown = (
            self.peak_portfolio_value - portfolio_value
        ) / self.peak_portfolio_value

        if self.current_drawdown > self.max_drawdown_pct:
            return [
                RiskViolation(
                    violation_type=RiskViolationType.DRAWDOWN_LIMIT,
                    current_value=self.current_drawdown,
                    limit_value=self.max_drawdown_pct,
                    description=(
                        "Portfolio drawdown {dd:.1%} exceeds limit {limit:.1%}".format(
                            dd=self.current_drawdown, limit=self.max_drawdown_pct
                        )
                    ),
                    timestamp=timestamp,
                )
            ]

        return []


class VolatilityControl:
    """Compute realized volatility over a sliding window."""

    def __init__(
        self,
        max_portfolio_volatility: float,
        *,
        lookback: int,
        min_samples: int,
        history: Optional[List[Tuple[int, float]]] = None,
    ) -> None:
        self.max_portfolio_volatility = max_portfolio_volatility
        self.lookback = lookback
        self.min_samples = min_samples
        self._history = history if history is not None else []

    @property
    def history(self) -> List[Tuple[int, float]]:
        """Return the tracked portfolio value history."""

        return self._history

    def update(self, timestamp: int, portfolio_value: float) -> List[RiskViolation]:
        """Record portfolio value and emit volatility violations when breached."""

        self._history.append((timestamp, portfolio_value))
        if len(self._history) < 2 or portfolio_value <= 0:
            return []

        recent_history = self._history[-self.lookback :]
        returns = _compute_returns(recent_history)

        if len(returns) >= self.min_samples:
            volatility = _annualized_volatility(returns)
            if volatility > self.max_portfolio_volatility:
                return [
                    RiskViolation(
                        violation_type=RiskViolationType.VOLATILITY_LIMIT,
                        current_value=volatility,
                        limit_value=self.max_portfolio_volatility,
                        description=(
                            "Portfolio volatility {vol:.1%} exceeds limit {limit:.1%}".format(
                                vol=volatility, limit=self.max_portfolio_volatility
                            )
                        ),
                        timestamp=recent_history[-1][0],
                    )
                ]

        return []


def _compute_returns(history: Iterable[Tuple[int, float]]) -> List[float]:
    """Compute discrete returns from portfolio history."""

    returns: List[float] = []
    history_list = list(history)
    for idx in range(1, len(history_list)):
        prev_value = history_list[idx - 1][1]
        curr_value = history_list[idx][1]
        if prev_value > 0:
            returns.append((curr_value - prev_value) / prev_value)
    return returns


def _annualized_volatility(returns: Iterable[float]) -> float:
    """Calculate annualized volatility assuming daily observations."""

    returns_list = list(returns)
    if not returns_list:
        return 0.0

    mean_return = sum(returns_list) / len(returns_list)
    variance = sum((r - mean_return) ** 2 for r in returns_list) / len(returns_list)
    return math.sqrt(variance) * math.sqrt(252)


__all__ = [
    "evaluate_position_size",
    "evaluate_leverage",
    "evaluate_concentration",
    "DrawdownControl",
    "VolatilityControl",
]
