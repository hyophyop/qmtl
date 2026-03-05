"""Automatic metrics pipeline for strategy submission.

WorldService is the SSOT for validation policy/rules. Runner/SDK only computes
metrics from backtest returns and forwards them to the authoritative service.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Dict, List, Sequence

if TYPE_CHECKING:
    from .strategy import Strategy

from qmtl.runtime.transforms.alpha_performance import alpha_performance_node
from qmtl.runtime.transforms.linearity_metrics import equity_linearity_metrics_v2

from .presets import PolicyPreset, get_preset

logger = logging.getLogger(__name__)


class ValidationStatus(StrEnum):
    """Validation pipeline status."""

    PENDING = "pending"
    VALIDATING = "validating"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


@dataclass
class PerformanceMetrics:
    """Calculated performance metrics from backtest."""

    sharpe: float = 0.0
    max_drawdown: float = 0.0
    win_ratio: float = 0.0
    profit_factor: float = 0.0
    car_mdd: float = 0.0
    rar_mdd: float = 0.0
    total_return: float = 0.0
    num_trades: int = 0
    avg_trade_return: float = 0.0
    monotonicity: float | None = None
    linearity_score: float | None = None
    t_slope: float | None = None
    t_slope_sig: float | None = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PerformanceMetrics":
        """Create from raw metrics dict."""
        return cls(
            sharpe=float(data.get("sharpe", 0.0)),
            max_drawdown=float(data.get("max_drawdown", 0.0)),
            win_ratio=float(data.get("win_ratio", 0.0)),
            profit_factor=float(data.get("profit_factor", 0.0)),
            car_mdd=float(data.get("car_mdd", 0.0)),
            rar_mdd=float(data.get("rar_mdd", 0.0)),
            total_return=float(data.get("total_return", 0.0)),
            num_trades=int(data.get("num_trades", 0)),
            avg_trade_return=float(data.get("avg_trade_return", 0.0)),
            monotonicity=data.get("monotonicity"),
            linearity_score=data.get("linearity_score"),
            t_slope=data.get("t_slope"),
            t_slope_sig=data.get("t_slope_sig"),
        )

    def to_policy_metrics(self) -> Dict[str, float]:
        """Convert to format expected by policy engine."""
        return {
            "sharpe": self.sharpe,
            "max_drawdown": abs(self.max_drawdown),  # Policy uses positive values
            "win_rate": self.win_ratio,  # Alias for win_ratio
            "win_ratio": self.win_ratio,
            "profit_factor": self.profit_factor,
            "car_mdd": self.car_mdd,
            "rar_mdd": self.rar_mdd,
            "el_v2_spearman_rho": self.monotonicity if self.monotonicity is not None else 0.0,
            "el_v2_score": self.linearity_score if self.linearity_score is not None else 0.0,
            "el_v2_t_slope": self.t_slope if self.t_slope is not None else 0.0,
            "el_v2_t_slope_sig": self.t_slope_sig if self.t_slope_sig is not None else 0.0,
        }


@dataclass
class ThresholdViolation:
    """Details of a threshold violation."""

    metric: str
    value: float
    threshold_type: str  # "min" or "max"
    threshold_value: float
    message: str


@dataclass
class ValidationResult:
    """Result of validation pipeline execution.

    Contains:
    - Validation status (passed/failed/error)
    - Performance metrics from backtest
    - Threshold violations (if any)
    - Improvement hints for failed strategies
    - Activation info for passed strategies
    """

    status: ValidationStatus
    metrics: PerformanceMetrics
    strategy_id: str
    world_id: str

    # Threshold violations (for failed validations)
    violations: List[ThresholdViolation] = field(default_factory=list)

    # Improvement hints
    improvement_hints: List[str] = field(default_factory=list)

    # Activation info (for passed validations)
    activated: bool = False
    weight: float = 0.0
    rank: int = 0
    contribution: float = 0.0

    # Correlation with existing strategies
    correlation_avg: float = 0.0
    correlation_violations: List[str] = field(default_factory=list)

    # Error info
    error_message: str | None = None

    @property
    def passed(self) -> bool:
        """Check if validation passed."""
        return self.status == ValidationStatus.PASSED

    @property
    def failed(self) -> bool:
        """Check if validation failed."""
        return self.status == ValidationStatus.FAILED


def _calculate_metrics_from_returns(
    returns: Sequence[float],
    *,
    risk_free_rate: float = 0.0,
    transaction_cost: float = 0.0,
) -> PerformanceMetrics:
    """Backward-compatible alias for `calculate_performance_metrics()`."""
    return calculate_performance_metrics(
        returns,
        risk_free_rate=risk_free_rate,
        transaction_cost=transaction_cost,
    )


def calculate_performance_metrics(
    returns: Sequence[float],
    *,
    risk_free_rate: float = 0.0,
    transaction_cost: float = 0.0,
) -> PerformanceMetrics:
    """Calculate performance metrics from a return series.

    This function only computes metrics (SSOT-safe) and does not evaluate
    any WorldService policies/rules.
    """
    if not returns:
        return PerformanceMetrics()

    # Filter out NaN values
    clean_returns = [r for r in returns if not math.isnan(r)]
    if not clean_returns:
        return PerformanceMetrics()

    raw_metrics = alpha_performance_node(
        clean_returns,
        risk_free_rate=risk_free_rate,
        transaction_cost=transaction_cost,
    )

    # Calculate additional metrics
    total_return = sum(clean_returns)
    num_trades = len(clean_returns)
    avg_trade_return = total_return / num_trades if num_trades > 0 else 0.0

    # alpha_performance_node returns keys with "alpha_performance." prefix
    # We need to extract values with or without the prefix
    def get_metric(key: str) -> float:
        """Get metric value, checking both prefixed and non-prefixed keys."""
        if key in raw_metrics:
            return float(raw_metrics[key])
        prefixed_key = f"alpha_performance.{key}"
        if prefixed_key in raw_metrics:
            return float(raw_metrics[prefixed_key])
        return 0.0

    linearity = _linearity_metrics_from_returns(clean_returns)

    return PerformanceMetrics(
        sharpe=get_metric("sharpe"),
        max_drawdown=get_metric("max_drawdown"),
        win_ratio=get_metric("win_ratio"),
        profit_factor=get_metric("profit_factor"),
        car_mdd=get_metric("car_mdd"),
        rar_mdd=get_metric("rar_mdd"),
        total_return=total_return,
        num_trades=num_trades,
        avg_trade_return=avg_trade_return,
        monotonicity=linearity.get("el_v2_spearman_rho"),
        linearity_score=linearity.get("el_v2_score"),
        t_slope=linearity.get("el_v2_t_slope"),
        t_slope_sig=linearity.get("el_v2_t_slope_sig"),
    )


def _linearity_metrics_from_returns(returns: Sequence[float]) -> Dict[str, float]:
    """Compute linearity/monotonicity metrics used by WS policy engine."""
    if not returns:
        return {}
    equity: list[float] = []
    cumulative = 0.0
    for value in returns:
        if math.isnan(value):
            continue
        cumulative += float(value)
        equity.append(cumulative)
    if len(equity) < 2:
        return {}
    metrics = equity_linearity_metrics_v2(equity)
    return {
        "el_v2_score": float(metrics.get("score", 0.0)),
        "el_v2_spearman_rho": float(metrics.get("spearman_rho", 0.0)),
        "el_v2_t_slope": float(metrics.get("t_slope", 0.0)),
        "el_v2_t_slope_sig": float(metrics.get("t_slope_sig", 0.0)),
    }


class ValidationPipeline:
    """Compute submission metrics before WorldService evaluation.

    The pipeline:
    1. Resolves or extracts a return series
    2. Calculates performance metrics locally
    3. Returns a neutral metrics result for WorldService-backed evaluation
    """

    def __init__(
        self,
        *,
        preset: PolicyPreset | str | None = None,
        world_id: str = "__default__",
    ):
        """Initialize a metrics-only validation helper."""
        self.world_id = world_id
        self.metrics_only = True
        _ = get_preset(preset) if preset is not None else None

    async def validate(
        self,
        strategy: "Strategy",
        *,
        returns: Sequence[float] | None = None,
        risk_free_rate: float = 0.0,
        transaction_cost: float = 0.0,
    ) -> ValidationResult:
        """Run validation pipeline on a strategy.

        Args:
            strategy: Strategy instance to validate
            returns: Backtest returns (if None, attempts to extract from strategy)
            risk_free_rate: Risk-free rate for Sharpe calculation
            transaction_cost: Transaction cost per trade

        Returns:
            ValidationResult with status, metrics, and activation info
        """
        strategy_id = getattr(strategy, "name", None) or type(strategy).__name__

        try:
            returns = self._resolve_returns(strategy, returns)
            metrics = self._calculate_metrics(returns, risk_free_rate, transaction_cost)

            if not returns:
                return ValidationResult(
                    status=ValidationStatus.ERROR,
                    metrics=metrics,
                    strategy_id=strategy_id,
                    world_id=self.world_id,
                    error_message="no returns available for metrics calculation",
                    improvement_hints=[
                        "Provide returns explicitly via validate(strategy, returns=...)",
                        "Or ensure the strategy exposes returns/equity/pnl fields",
                    ],
                )

            return ValidationResult(
                status=ValidationStatus.PASSED,
                metrics=metrics,
                strategy_id=strategy_id,
                world_id=self.world_id,
                violations=[],
                improvement_hints=[],
                activated=False,
                weight=0.0,
                rank=0,
                contribution=0.0,
                correlation_avg=0.0,
                correlation_violations=[],
            )

        except Exception as e:
            logger.exception(f"Validation error for strategy {strategy_id}")
            return ValidationResult(
                status=ValidationStatus.ERROR,
                metrics=PerformanceMetrics(),
                strategy_id=strategy_id,
                world_id=self.world_id,
                error_message=str(e),
                improvement_hints=[f"Validation error: {e}"],
            )

    def _resolve_returns(
        self, strategy: "Strategy", provided_returns: Sequence[float] | None
    ) -> Sequence[float]:
        if provided_returns is not None:
            return provided_returns
        return self._extract_returns_from_strategy(strategy)

    def _calculate_metrics(
        self,
        returns: Sequence[float],
        risk_free_rate: float,
        transaction_cost: float,
    ) -> PerformanceMetrics:
        return calculate_performance_metrics(
            returns,
            risk_free_rate=risk_free_rate,
            transaction_cost=transaction_cost,
        )

    def _extract_returns_from_strategy(
        self,
        strategy: "Strategy",
    ) -> Sequence[float]:
        """Attempt to extract returns from a strategy instance.

        Looks for common patterns:
        - strategy.returns
        - strategy.equity (converts to returns)
        - strategy.pnl
        """
        # Try returns directly
        if hasattr(strategy, "returns") and strategy.returns:
            return list(strategy.returns)

        # Try equity curve (convert to returns)
        if hasattr(strategy, "equity") and strategy.equity:
            equity = list(strategy.equity)
            if len(equity) < 2:
                return []
            returns = []
            for i in range(1, len(equity)):
                if equity[i - 1] != 0:
                    returns.append((equity[i] - equity[i - 1]) / equity[i - 1])
                else:
                    returns.append(0.0)
            return returns

        # Try PnL
        if hasattr(strategy, "pnl") and strategy.pnl:
            return list(strategy.pnl)

        # No returns found - return empty
        logger.warning(
            f"Could not extract returns from strategy {type(strategy).__name__}. "
            "Provide returns explicitly via validate(strategy, returns=...)"
        )
        return []

    def validate_sync(
        self,
        strategy: "Strategy",
        *,
        returns: Sequence[float] | None = None,
        risk_free_rate: float = 0.0,
        transaction_cost: float = 0.0,
    ) -> ValidationResult:
        """Synchronous wrapper around validate()."""
        import asyncio

        return asyncio.run(
            self.validate(
                strategy,
                returns=returns,
                risk_free_rate=risk_free_rate,
                transaction_cost=transaction_cost,
            )
        )


# Convenience functions for quick validation
async def validate_strategy(
    strategy: "Strategy",
    *,
    returns: Sequence[float] | None = None,
    preset: PolicyPreset | str = PolicyPreset.SANDBOX,
    world_id: str = "__default__",
) -> ValidationResult:
    """Validate a strategy with default settings.

    This is a convenience function for quick validation without
    creating a ValidationPipeline instance.

    Args:
        strategy: Strategy to validate
        returns: Backtest returns
        preset: Policy preset to use
        world_id: Target world

    Returns:
        ValidationResult
    """
    pipeline = ValidationPipeline(preset=preset, world_id=world_id)
    return await pipeline.validate(strategy, returns=returns)


def validate_strategy_sync(
    strategy: "Strategy",
    *,
    returns: Sequence[float] | None = None,
    preset: PolicyPreset | str = PolicyPreset.SANDBOX,
    world_id: str = "__default__",
) -> ValidationResult:
    """Synchronous version of validate_strategy()."""
    import asyncio

    return asyncio.run(
        validate_strategy(strategy, returns=returns, preset=preset, world_id=world_id)
    )


__all__ = [
    "ValidationStatus",
    "PerformanceMetrics",
    "ThresholdViolation",
    "ValidationResult",
    "ValidationPipeline",
    "calculate_performance_metrics",
    "validate_strategy",
    "validate_strategy_sync",
]
