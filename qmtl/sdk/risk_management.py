"""Risk management orchestration built on composable controls."""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, List, Optional, Sequence, Tuple

from .risk import (
    DrawdownControl,
    PortfolioScope,
    PositionInfo,
    RiskConfig,
    RiskViolation,
    RiskViolationType,
    VolatilityControl,
    aggregate_portfolios,
    evaluate_concentration,
    evaluate_leverage,
    evaluate_position_size,
)


class RiskManager:
    """Risk management system for backtesting."""

    def __init__(
        self,
        config: Optional[RiskConfig] = None,
        **config_overrides: object,
    ) -> None:
        """Create a :class:`RiskManager` using ``RiskConfig`` thresholds.

        Parameters
        ----------
        config:
            Optional base configuration. If omitted, :class:`RiskConfig` defaults
            are used.
        **config_overrides:
            Keyword arguments matching :class:`RiskConfig` fields to override
            either the provided ``config`` or the defaults.
        """

        base_config = config or RiskConfig()

        if config_overrides:
            unknown = set(config_overrides) - set(RiskConfig.__annotations__)
            if unknown:
                unknown_str = ", ".join(sorted(unknown))
                raise TypeError(f"Unknown risk config overrides: {unknown_str}")
            base_config = replace(base_config, **config_overrides)

        self.config = base_config
        self.violations: List[RiskViolation] = []
        self._drawdown_control = DrawdownControl(self.config.max_drawdown_pct)
        self._volatility_control = VolatilityControl(
            self.config.max_portfolio_volatility,
            lookback=self.config.volatility_lookback,
            min_samples=self.config.volatility_min_samples,
        )

    @property
    def portfolio_value_history(self) -> List[Tuple[int, float]]:
        """History of portfolio values observed by the manager."""

        return self._volatility_control.history

    @property
    def peak_portfolio_value(self) -> float:
        """Highest portfolio value observed so far."""

        return self._drawdown_control.peak_portfolio_value

    @property
    def max_position_size(self) -> Optional[float]:
        return self.config.max_position_size

    @property
    def max_leverage(self) -> float:
        return self.config.max_leverage

    @property
    def max_drawdown_pct(self) -> float:
        return self.config.max_drawdown_pct

    @property
    def max_concentration_pct(self) -> float:
        return self.config.max_concentration_pct

    @property
    def max_portfolio_volatility(self) -> float:
        return self.config.max_portfolio_volatility

    @property
    def position_size_limit_pct(self) -> float:
        return self.config.position_size_limit_pct

    @property
    def enable_dynamic_sizing(self) -> bool:
        return self.config.enable_dynamic_sizing

    def validate_position_size(
        self,
        symbol: str,
        proposed_quantity: float,
        current_price: float,
        portfolio_value: float,
        current_positions: Dict[str, PositionInfo],
    ) -> Tuple[bool, Optional[RiskViolation], float]:
        """Validate proposed position size against risk limits."""

        return evaluate_position_size(
            symbol,
            proposed_quantity,
            current_price,
            portfolio_value,
            current_positions,
            max_position_size=self.config.max_position_size,
            position_size_limit_pct=self.config.position_size_limit_pct,
            enable_dynamic_sizing=self.config.enable_dynamic_sizing,
        )

    def validate_portfolio_risk(
        self,
        positions: Dict[str, PositionInfo],
        portfolio_value: float,
        timestamp: int,
    ) -> List[RiskViolation]:
        """Validate overall portfolio risk metrics."""

        volatility_violations = self._volatility_control.update(
            timestamp, portfolio_value
        )
        violations: List[RiskViolation] = []

        if portfolio_value <= 0:
            self.violations.extend(volatility_violations)
            return volatility_violations

        total_exposure = sum(pos.exposure for pos in positions.values())
        leverage_violation = evaluate_leverage(
            total_exposure,
            portfolio_value,
            max_leverage=self.config.max_leverage,
            timestamp=timestamp,
        )
        if leverage_violation:
            violations.append(leverage_violation)

        violations.extend(
            evaluate_concentration(
                positions,
                portfolio_value,
                max_concentration_pct=self.config.max_concentration_pct,
                timestamp=timestamp,
            )
        )

        violations.extend(
            self._drawdown_control.update(portfolio_value, timestamp)
        )

        violations.extend(volatility_violations)

        self.violations.extend(violations)
        return violations

    def validate_world_risk(
        self,
        strategies: Sequence[Tuple[float, Dict[str, PositionInfo]]],
        timestamp: int,
    ) -> List[RiskViolation]:
        """Validate risk metrics across multiple strategies."""

        total_value, aggregated = aggregate_portfolios(strategies)
        return self.validate_portfolio_risk(aggregated, total_value, timestamp)

    def calculate_position_size(
        self,
        symbol: str,
        target_allocation_pct: float,
        current_price: float,
        portfolio_value: float,
        current_volatility: Optional[float] = None,
    ) -> float:
        """Calculate appropriate position size considering risk constraints."""

        if portfolio_value <= 0 or current_price <= 0:
            return 0.0

        base_allocation = min(
            target_allocation_pct, self.config.position_size_limit_pct
        )

        if current_volatility and current_volatility > 0:
            volatility_adjustment = min(1.0, 0.20 / current_volatility)
            adjusted_allocation = base_allocation * volatility_adjustment
        else:
            adjusted_allocation = base_allocation

        target_value = portfolio_value * adjusted_allocation
        return target_value / current_price

    def get_risk_summary(self) -> Dict[str, object]:
        """Get summary of risk metrics and violations."""

        return {
            "total_violations": len(self.violations),
            "violation_types": {
                vtype.value: len(
                    [v for v in self.violations if v.violation_type == vtype]
                )
                for vtype in RiskViolationType
            },
            "critical_violations": len(
                [v for v in self.violations if v.severity == "critical"]
            ),
            "high_violations": len(
                [v for v in self.violations if v.severity == "high"]
            ),
            "peak_portfolio_value": self.peak_portfolio_value,
            "current_drawdown": self._drawdown_control.current_drawdown,
            "risk_config": {
                "max_leverage": self.config.max_leverage,
                "max_drawdown_pct": self.config.max_drawdown_pct,
                "max_concentration_pct": self.config.max_concentration_pct,
                "position_size_limit_pct": self.config.position_size_limit_pct,
            },
        }


__all__ = [
    "PortfolioScope",
    "RiskViolationType",
    "RiskViolation",
    "PositionInfo",
    "RiskConfig",
    "aggregate_portfolios",
    "RiskManager",
]
