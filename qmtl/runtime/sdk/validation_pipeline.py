"""Automatic validation pipeline for strategy submission.

This module implements Phase 2 of the QMTL simplification proposal:
1. Auto-trigger backtest on submission
2. Calculate performance metrics automatically
3. Threshold-based auto-activation/rejection

The pipeline evaluates strategies against policy thresholds and
determines if they should be activated in the target world.
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
from qmtl.services.worldservice.policy_engine import (
    Policy,
    ThresholdRule,
    TopKRule,
    CorrelationRule,
    HysteresisRule,
    evaluate_policy,
)

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
    """Calculate performance metrics from a return series."""
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


def _policy_from_preset(preset: PresetPolicy) -> Policy:
    """Convert PresetPolicy to WorldService Policy."""
    thresholds = {
        t.metric: ThresholdRule(metric=t.metric, min=t.min, max=t.max)
        for t in preset.thresholds
    }
    top_k = None
    if preset.top_k:
        top_k = TopKRule(metric=preset.top_k.metric, k=preset.top_k.k)
    correlation = None
    if preset.correlation:
        correlation = CorrelationRule(max=preset.correlation.max)
    hysteresis = None
    if preset.hysteresis:
        hysteresis = HysteresisRule(
            metric=preset.hysteresis.metric,
            enter=preset.hysteresis.enter,
            exit=preset.hysteresis.exit,
        )
    return Policy(
        thresholds=thresholds,
        top_k=top_k,
        correlation=correlation,
        hysteresis=hysteresis,
    )


def _check_thresholds(
    metrics: PerformanceMetrics,
    policy: PresetPolicy | Policy,
) -> List[ThresholdViolation]:
    """Check metrics against policy thresholds (for hints)."""
    violations: List[ThresholdViolation] = []
    metric_values = metrics.to_policy_metrics()

    thresholds: Iterable[ThresholdConfig | ThresholdRule]
    if isinstance(policy, PresetPolicy):
        thresholds = policy.thresholds
    else:
        thresholds = policy.thresholds.values()

    for threshold in thresholds:
        if isinstance(threshold, ThresholdRule):
            metric_name = threshold.metric
            min_val = threshold.min
            max_val = threshold.max
        else:
            metric_name = threshold.metric
            min_val = threshold.min
            max_val = threshold.max

        current_value = metric_values.get(metric_name, 0.0)

        if min_val is not None and current_value < min_val:
            violations.append(
                ThresholdViolation(
                    metric=metric_name,
                    value=current_value,
                    threshold_type="min",
                    threshold_value=min_val,
                    message=f"{metric_name} ({current_value:.4f}) is below minimum ({min_val})",
                )
            )

        if max_val is not None and current_value > max_val:
            violations.append(
                ThresholdViolation(
                    metric=metric_name,
                    value=current_value,
                    threshold_type="max",
                    threshold_value=max_val,
                    message=f"{metric_name} ({current_value:.4f}) is above maximum ({max_val})",
                )
            )

    return violations


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
    """Generate actionable improvement hints based on violations."""
    if not violations:
        return []
    handlers = {
        "sharpe": _hint_sharpe,
        "max_drawdown": _hint_max_drawdown,
        "win_rate": _hint_win_rate,
        "win_ratio": _hint_win_rate,
        "profit_factor": _hint_profit_factor,
        "equity_monotonicity": _hint_equity_monotonicity,
    }
    hints: List[str] = []
    for v in violations:
        handler = handlers.get(v.metric)
        if handler:
            text = handler(v)
            if text:
                hints.append(text)
    if hints:
        return hints
    return [
        "Review the threshold violations above and adjust your strategy parameters accordingly."
    ]


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
    policy: PresetPolicy | Policy,
) -> tuple[float, int]:
    """Calculate portfolio weight and rank for a new strategy.

    Uses a simple Sharpe-based weighting scheme:
    - Weight is proportional to Sharpe ratio
    - Rank is based on Sharpe among all strategies
    """
    all_sharpes = {
        sid: m.get("sharpe", 0.0) for sid, m in existing_strategies.items()
    }
    all_sharpes[strategy_id] = metrics.sharpe

    # Calculate rank (1 = best)
    sorted_strategies = sorted(
        all_sharpes.items(),
        key=lambda x: x[1],
        reverse=True,
    )
    rank = next(
        (i + 1 for i, (sid, _) in enumerate(sorted_strategies) if sid == strategy_id),
        len(sorted_strategies),
    )

    # Calculate weight (Sharpe-proportional, normalized)
    total_sharpe = sum(max(s, 0.0) for s in all_sharpes.values())
    if total_sharpe > 0:
        weight = max(metrics.sharpe, 0.0) / total_sharpe
    else:
        weight = 1.0 / len(all_sharpes)

    # Apply max_strategies limit
    max_strategies = getattr(policy, "max_strategies", 10)
    if rank > max_strategies:
        weight = 0.0

    return weight, rank


def _estimate_contribution(
    weight: float,
    metrics: PerformanceMetrics,
    world_sharpe: float = 1.0,
) -> float:
    """Estimate strategy contribution to world returns.

    Contribution = weight × (strategy_sharpe / world_sharpe)

    This is an approximation; actual contribution depends on
    correlation with other strategies.
    """
    if world_sharpe <= 0:
        world_sharpe = 1.0

    return weight * (metrics.sharpe / world_sharpe)


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
    3. Validates against policy thresholds
    4. Determines activation status and weight

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
        policy: Policy | None = None,
        world_id: str = "__default__",
        existing_strategies: Dict[str, Dict[str, float]] | None = None,
        existing_returns: Dict[str, Sequence[float]] | None = None,
        world_sharpe: float = 1.0,
    ):
        """Initialize validation pipeline.

        Args:
            preset: Policy preset to use (sandbox/conservative/moderate/aggressive)
            policy: Custom policy (overrides preset)
            world_id: Target world ID
            existing_strategies: Metrics of existing strategies in world
            existing_returns: Returns of existing strategies for correlation calculation
            world_sharpe: Current world Sharpe ratio for contribution estimation
        """
        if policy is not None:
            self.policy: Policy | None = policy
            self.preset_policy: PresetPolicy | None = None
        elif preset is not None:
            self.preset_policy = get_preset(preset)
            self.policy = _policy_from_preset(self.preset_policy)
        else:
            self.preset_policy = get_preset(PolicyPreset.SANDBOX)
            self.policy = _policy_from_preset(self.preset_policy)

        self.world_id = world_id
        self.existing_strategies = existing_strategies or {}
        self.existing_returns = existing_returns or {}
        self.world_sharpe = world_sharpe

    def _get_effective_policy(self) -> PresetPolicy | Policy:
        """Get the effective policy for validation."""
        if self.policy is not None:
            return self.policy
        if self.preset_policy is not None:
            return self.preset_policy
        return get_preset(PolicyPreset.SANDBOX)

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

            policy = self._get_effective_policy()
            policy_obj = policy if isinstance(policy, Policy) else _policy_from_preset(policy)

            violations = self._collect_metric_violations(metrics, policy_obj)
            correlation_avg, correlation_flags, correlation_thresholds = self._collect_correlation(
                returns, policy_obj
            )
            if correlation_thresholds:
                violations.extend(correlation_thresholds)

            is_active = self._is_policy_active(strategy_id, metrics, policy_obj)
            if violations or not is_active:
                return self._build_failure_result(
                    strategy_id,
                    metrics,
                    violations,
                    correlation_avg,
                    correlation_flags,
                )

            weight, rank = _calculate_weight_and_rank(
                strategy_id,
                metrics,
                self.existing_strategies,
                policy,
            )
            contribution = _estimate_contribution(weight, metrics, self.world_sharpe)

            return ValidationResult(
                status=ValidationStatus.PASSED,
                metrics=metrics,
                strategy_id=strategy_id,
                world_id=self.world_id,
                activated=weight > 0,
                weight=weight,
                rank=rank,
                contribution=contribution,
                correlation_avg=correlation_avg,
                correlation_violations=correlation_flags,
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
        return _calculate_metrics_from_returns(
            returns,
            risk_free_rate=risk_free_rate,
            transaction_cost=transaction_cost,
        )

    def _collect_metric_violations(
        self, metrics: PerformanceMetrics, policy: Policy
    ) -> List[ThresholdViolation]:
        violations = _check_thresholds(metrics, policy)
        monotonic_violation = _monotonicity_violation(metrics.monotonicity)
        if monotonic_violation:
            violations.insert(0, monotonic_violation)
        return violations

    def _collect_correlation(
        self,
        returns: Sequence[float],
        policy: Policy,
    ) -> tuple[float, list[str], list[ThresholdViolation]]:
        if not (self.existing_returns and returns):
            return 0.0, [], []

        correlation_avg, correlation_violations = _calculate_correlation(
            returns, self.existing_returns
        )
        threshold_violations: list[ThresholdViolation] = []
        if policy.correlation and correlation_avg > policy.correlation.max:
            threshold_violations.append(
                ThresholdViolation(
                    metric="correlation_avg",
                    value=correlation_avg,
                    threshold_type="max",
                    threshold_value=policy.correlation.max,
                    message=(
                        f"Average correlation ({correlation_avg:.2f}) exceeds maximum "
                        f"({policy.correlation.max})"
                    ),
                )
            )
        return correlation_avg, correlation_violations, threshold_violations

    def _is_policy_active(
        self,
        strategy_id: str,
        metrics: PerformanceMetrics,
        policy: Policy,
    ) -> bool:
        metrics_dict = {strategy_id: metrics.to_policy_metrics()}
        active = evaluate_policy(metrics_dict, policy)
        return strategy_id in active

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
    "validate_strategy",
    "validate_strategy_sync",
]
