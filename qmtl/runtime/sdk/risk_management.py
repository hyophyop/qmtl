"""Risk management orchestration built on composable controls."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .risk import (
    DrawdownControl,
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
        **config_overrides: Any,
    ) -> None:
        base_config = config or RiskConfig()
        self.config = _apply_override_values(base_config, config_overrides)
        self.violations: List[RiskViolation] = []
        self._drawdown_control = DrawdownControl(self.config.max_drawdown_pct)
        self._volatility_control = VolatilityControl(
            self.config.max_portfolio_volatility,
            lookback=self.config.volatility_lookback,
            min_samples=self.config.volatility_min_samples,
        )

    @property
    def portfolio_value_history(self) -> List[Tuple[int, float]]:
        return self._volatility_control.history

    @portfolio_value_history.setter
    def portfolio_value_history(self, values: Sequence[Tuple[int, float]]) -> None:
        history_list = list(values)
        self._volatility_control.history = history_list

        if not history_list:
            self._drawdown_control.current_drawdown = 0.0
            return

        peak_value = self._drawdown_control.peak_portfolio_value
        if peak_value <= 0:
            peak_value = max(value for _, value in history_list)
            self._drawdown_control.peak_portfolio_value = peak_value

        current_value = history_list[-1][1]
        if peak_value > 0:
            self._drawdown_control.current_drawdown = (peak_value - current_value) / peak_value
        else:
            self._drawdown_control.current_drawdown = 0.0

    @property
    def peak_portfolio_value(self) -> float:
        return self._drawdown_control.peak_portfolio_value

    @peak_portfolio_value.setter
    def peak_portfolio_value(self, value: float) -> None:
        self._drawdown_control.peak_portfolio_value = value
        history = self._volatility_control.history
        if history and value > 0:
            current_value = history[-1][1]
            self._drawdown_control.current_drawdown = (value - current_value) / value
        elif value <= 0:
            self._drawdown_control.current_drawdown = 0.0

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
        volatility_violations = self._volatility_control.update(timestamp, portfolio_value)
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
            evaluate_portfolios_for_drawdown(
                positions,
                portfolio_value,
                drawdown_control=self._drawdown_control,
                timestamp=timestamp,
            )
        )

        violations.extend(volatility_violations)
        self.violations.extend(violations)
        return violations

    def validate_world_risk(
        self,
        strategies: Sequence[Tuple[float, Dict[str, PositionInfo]]],
        timestamp: int,
    ) -> List[RiskViolation]:
        if not strategies:
            return []
        total_value, aggregated_positions = aggregate_portfolios(strategies)
        return self.validate_portfolio_risk(
            positions=aggregated_positions,
            portfolio_value=total_value,
            timestamp=timestamp,
        )

    def calculate_position_size(
        self,
        *,
        symbol: str,
        target_allocation_pct: float,
        current_price: float,
        portfolio_value: float,
        current_volatility: float | None = None,
    ) -> float:
        if portfolio_value <= 0 or current_price <= 0:
            return 0.0

        base_qty = (target_allocation_pct * portfolio_value) / current_price
        if base_qty <= 0:
            return 0.0

        vol_factor = max(current_volatility or 0.0, 0.0)
        adjusted_qty = base_qty / (1.0 + vol_factor)

        if self.position_size_limit_pct > 0:
            limit_qty = (self.position_size_limit_pct * portfolio_value) / current_price
            return min(adjusted_qty, limit_qty)
        return adjusted_qty

    def get_risk_summary(self) -> Dict[str, Any]:
        violation_types: Dict[str, int] = {}
        for violation in self.violations:
            violation_types[violation.violation_type.value] = (
                violation_types.get(violation.violation_type.value, 0) + 1
            )

        summary: Dict[str, Any] = {
            "total_violations": len(self.violations),
            "violation_types": violation_types,
            "peak_portfolio_value": float(self._drawdown_control.peak_portfolio_value),
            "current_drawdown": float(self._drawdown_control.current_drawdown),
            "risk_config": self.config.__dict__.copy(),
        }
        return summary

    def _check_volatility_limit(self, timestamp: int) -> List[RiskViolation]:
        if not self._volatility_control.history:
            return []
        last_value = self._volatility_control.history[-1][1]
        return self._volatility_control.update(timestamp, last_value)


def _apply_override_values(base_config: RiskConfig, overrides: dict[str, Any]) -> RiskConfig:
    if not overrides:
        return base_config

    _validate_override_keys(overrides)

    field_specs: dict[str, tuple[type, bool]] = {
        "max_position_size": (float, True),
        "max_leverage": (float, False),
        "max_drawdown_pct": (float, False),
        "max_concentration_pct": (float, False),
        "max_portfolio_volatility": (float, False),
        "position_size_limit_pct": (float, False),
        "enable_dynamic_sizing": (bool, False),
        "volatility_lookback": (int, False),
        "volatility_min_samples": (int, False),
    }

    updates: dict[str, Any] = {}
    for key, value in overrides.items():
        spec = field_specs.get(key)
        if not spec:
            continue

        caster, allow_none = spec
        if value is None and not allow_none:
            continue

        updates[key] = None if value is None else caster(value)

    if not updates:
        return base_config

    return replace(base_config, **updates)


def _validate_override_keys(overrides: dict[str, Any]) -> None:
    unknown = set(overrides) - set(RiskConfig.__annotations__)
    if unknown:
        unknown_str = ", ".join(sorted(unknown))
        raise TypeError(f"Unknown risk config overrides: {unknown_str}")


def evaluate_portfolios_for_drawdown(
    positions: Dict[str, PositionInfo],
    portfolio_value: float,
    drawdown_control: DrawdownControl,
    timestamp: int,
) -> List[RiskViolation]:
    return drawdown_control.update(portfolio_value, timestamp)
