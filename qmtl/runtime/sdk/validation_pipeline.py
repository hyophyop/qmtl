"""Automatic validation pipeline for strategy submission.

This module implements Phase 2 of the QMTL simplification proposal:
1. Auto-trigger backtest on submission
2. Calculate performance metrics automatically
3. (Deprecated) threshold-based pre-checks

As of World Validation v1.5, WorldService is the SSOT for validation policy/rules.
Runner/SDK should only compute metrics and submit them.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Sequence

if TYPE_CHECKING:
    from .strategy import Strategy

from qmtl.runtime.transforms.alpha_performance import alpha_performance_node
from qmtl.runtime.transforms.linearity_metrics import equity_linearity_metrics_v2

from .presets import PolicyPreset, PresetPolicy, ThresholdConfig, get_preset

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


def _policy_from_preset(preset: PresetPolicy) -> dict[str, Any]:
    """Deprecated: local Policy materialization is no longer supported."""
    _ = preset
    return {}


def _check_thresholds(
    metrics: PerformanceMetrics,
    policy: Any,
) -> List[ThresholdViolation]:
    """Deprecated: local threshold checks are no longer supported (WS is SSOT)."""
    _ = (metrics, policy)
    return []


def _monotonicity_violation(monotonicity: float | None) -> ThresholdViolation | None:
    """Generate monotonicity violation when equity curve is trending downward."""
    if monotonicity is None:
        return None
    if monotonicity < 0:
        return ThresholdViolation(
            metric="equity_monotonicity",
            value=monotonicity,
            threshold_type="min",
            threshold_value=0.0,
            message=f"Equity curve monotonicity below 0 (Spearman rho={monotonicity:.2f})",
        )
    return None


def _generate_improvement_hints(violations: List[ThresholdViolation]) -> List[str]:
    """Deprecated: use WorldService results for actionable hints."""
    _ = violations
    return []


def _hint_sharpe(v: ThresholdViolation) -> str | None:
    if v.threshold_type == "min":
        return (
            f"Improve Sharpe ratio: current {v.value:.2f}, need ≥{v.threshold_value}. "
            "Consider reducing volatility or increasing returns."
        )
    return None


def _hint_max_drawdown(v: ThresholdViolation) -> str | None:
    if v.threshold_type == "max":
        return (
            f"Reduce max drawdown: current {v.value:.1%}, need ≤{v.threshold_value:.1%}. "
            "Consider adding stop-loss or reducing position sizes."
        )
    return None


def _hint_win_rate(v: ThresholdViolation) -> str | None:
    if v.threshold_type == "min":
        return (
            f"Improve win rate: current {v.value:.1%}, need ≥{v.threshold_value:.1%}. "
            "Consider refining entry signals or filtering low-probability trades."
        )
    return None


def _hint_profit_factor(v: ThresholdViolation) -> str | None:
    if v.threshold_type == "min":
        return (
            f"Improve profit factor: current {v.value:.2f}, need ≥{v.threshold_value}. "
            "Consider improving risk/reward ratio or cutting losses faster."
        )
    return None


def _hint_equity_monotonicity(_: ThresholdViolation) -> str:
    return (
        "Stabilize the equity curve: current monotonicity is negative. "
        "Consider reducing choppiness or enforcing risk controls to avoid repeated drawdowns."
    )


def _calculate_weight_and_rank(
    strategy_id: str,
    metrics: PerformanceMetrics,
    existing_strategies: Dict[str, Dict[str, float]],
    policy: Any,
) -> tuple[float, int]:
    """Deprecated: local selection/weighting is no longer supported (WS is SSOT)."""
    _ = (strategy_id, metrics, existing_strategies, policy)
    return 0.0, 0


def _estimate_contribution(
    weight: float,
    metrics: PerformanceMetrics,
    world_sharpe: float = 1.0,
) -> float:
    """Deprecated: local contribution estimates are no longer supported (WS is SSOT)."""
    _ = (weight, metrics, world_sharpe)
    return 0.0


def _calculate_correlation(
    new_returns: Sequence[float],
    existing_returns: Dict[str, Sequence[float]],
) -> tuple[float, List[str]]:
    """Calculate correlation between new strategy and existing strategies.

    Args:
        new_returns: Returns of the new strategy.
        existing_returns: Dict mapping strategy_id to returns sequence.

    Returns:
        Tuple of (average_correlation, list of strategy IDs exceeding threshold).
    """
    if not existing_returns or not new_returns:
        return 0.0, []

    clean_new = _clean_series(new_returns)
    if len(clean_new) < 2:
        return 0.0, []

    correlations: List[float] = []
    high_correlation_strategies: List[str] = []

    for sid, returns in existing_returns.items():
        corr = _pairwise_correlation(clean_new, returns)
        if corr is None:
            continue
        correlations.append(abs(corr))
        if abs(corr) > 0.7:
            high_correlation_strategies.append(sid)

    avg_corr = sum(correlations) / len(correlations) if correlations else 0.0
    return avg_corr, high_correlation_strategies


def _clean_series(values: Sequence[float]) -> List[float]:
    return [float(r) for r in values if not math.isnan(r)]


def _pairwise_correlation(new_arr: Sequence[float], existing: Sequence[float]) -> float | None:
    clean_existing = _clean_series(existing)
    min_len = min(len(new_arr), len(clean_existing))
    if min_len < 2:
        return None

    a = list(new_arr[:min_len])
    b = list(clean_existing[:min_len])
    mean_a = sum(a) / min_len
    mean_b = sum(b) / min_len

    numerator = sum((ai - mean_a) * (bi - mean_b) for ai, bi in zip(a, b))
    std_a = math.sqrt(sum((x - mean_a) ** 2 for x in a))
    std_b = math.sqrt(sum((x - mean_b) ** 2 for x in b))
    if std_a == 0 or std_b == 0:
        return None
    return numerator / (std_a * std_b)


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
    """Automatic validation pipeline for strategy submission.

    The pipeline:
    1. Runs backtest on historical data
    2. Calculates performance metrics
    3. (Deprecated) local policy evaluation

    Usage:
        pipeline = ValidationPipeline(preset="conservative")
        result = await pipeline.validate(strategy, returns=backtest_returns)

        if result.passed:
            print(f"Activated with weight {result.weight:.2%}")
        else:
            for hint in result.improvement_hints:
                print(hint)
    """

    def __init__(
        self,
        *,
        preset: PolicyPreset | str | None = None,
        policy: Any | None = None,
        world_id: str = "__default__",
        existing_strategies: Dict[str, Dict[str, float]] | None = None,
        existing_returns: Dict[str, Sequence[float]] | None = None,
        world_sharpe: float = 1.0,
        metrics_only: bool = False,
    ):
        """Initialize validation pipeline.

        Args:
            preset: Policy preset to use (sandbox/conservative/moderate/aggressive)
            policy: Deprecated (ignored)
            world_id: Target world ID
            existing_strategies: Deprecated (ignored)
            existing_returns: Deprecated (ignored)
            world_sharpe: Deprecated (ignored)
            metrics_only: Deprecated (ignored; always metrics-only)
        """
        self.world_id = world_id
        self.preset_policy: PresetPolicy | None = get_preset(preset) if preset is not None else None
        self.metrics_only = True

        _ = metrics_only
        if policy is not None or existing_strategies or existing_returns or world_sharpe != 1.0:
            logger.warning(
                "ValidationPipeline local policy evaluation is deprecated; "
                "Runner/SDK now only computes metrics. Use WorldService for evaluation.",
            )

    def _get_effective_policy(self) -> PresetPolicy:
        """Deprecated: WorldService is SSOT for policies."""
        return self.preset_policy or get_preset(PolicyPreset.SANDBOX)

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

    def _collect_metric_violations(
        self, metrics: PerformanceMetrics, policy: Any
    ) -> List[ThresholdViolation]:
        logger.warning("ValidationPipeline local policy evaluation is deprecated; use WorldService.")
        _ = (metrics, policy)
        return []

    def _collect_correlation(
        self,
        returns: Sequence[float],
        policy: Any,
    ) -> tuple[float, list[str], list[ThresholdViolation]]:
        logger.warning("ValidationPipeline local policy evaluation is deprecated; use WorldService.")
        _ = (returns, policy)
        return 0.0, [], []

    def _is_policy_active(
        self,
        strategy_id: str,
        metrics: PerformanceMetrics,
        policy: Any,
    ) -> bool:
        logger.warning("ValidationPipeline local policy evaluation is deprecated; use WorldService.")
        _ = (strategy_id, metrics, policy)
        return True

    def _build_failure_result(
        self,
        strategy_id: str,
        metrics: PerformanceMetrics,
        violations: list[ThresholdViolation],
        correlation_avg: float,
        correlation_violations: list[str],
    ) -> ValidationResult:
        return ValidationResult(
            status=ValidationStatus.FAILED,
            metrics=metrics,
            strategy_id=strategy_id,
            world_id=self.world_id,
            violations=violations,
            improvement_hints=_generate_improvement_hints(violations),
            activated=False,
            correlation_avg=correlation_avg,
            correlation_violations=correlation_violations,
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
