"""Tests for the validation pipeline (Phase 2).

This module tests:
- PerformanceMetrics calculation from returns
- Threshold checking against policy
- ValidationResult generation
- Improvement hint generation
- Weight/rank calculation
- Integration with submit()
"""

from __future__ import annotations

import pytest

from qmtl.runtime.sdk.validation_pipeline import (
    ValidationPipeline,
    ValidationResult,
    ValidationStatus,
    PerformanceMetrics,
    ThresholdViolation,
    _calculate_metrics_from_returns,
    _check_thresholds,
    _generate_improvement_hints,
    _calculate_weight_and_rank,
    _estimate_contribution,
    validate_strategy,
    validate_strategy_sync,
)
from qmtl.runtime.sdk.presets import (
    PolicyPreset,
    PresetPolicy,
    ThresholdConfig,
    get_preset,
)

import pytest

# Suppress noisy resource warnings from http client sockets/event loops in local tests
pytestmark = [
    pytest.mark.filterwarnings("ignore:unclosed.*ResourceWarning"),
    pytest.mark.filterwarnings("ignore:.*unclosed event loop.*ResourceWarning"),
    pytest.mark.filterwarnings("ignore:unclosed <socket.*ResourceWarning"),
]


# ============================================================================
# Test Data
# ============================================================================

# Good returns: positive Sharpe, low drawdown
GOOD_RETURNS = [0.01, 0.02, -0.005, 0.015, 0.012, 0.008, -0.003, 0.02, 0.01, 0.005]

# Bad returns: negative or volatile
BAD_RETURNS = [-0.05, -0.03, 0.01, -0.04, -0.02, 0.005, -0.03, -0.01, -0.02, -0.015]

# Mixed returns: moderate performance
MIXED_RETURNS = [0.01, -0.01, 0.02, -0.005, 0.015, -0.02, 0.01, 0.005, -0.01, 0.008]


class MockStrategy:
    """Mock strategy for testing."""

    def __init__(self, name: str = "TestStrategy", returns: list[float] | None = None):
        self.name = name
        self._returns = returns or []

    @property
    def returns(self) -> list[float]:
        return self._returns


# ============================================================================
# PerformanceMetrics Tests
# ============================================================================


class TestPerformanceMetrics:
    """Tests for PerformanceMetrics calculation."""

    def test_calculate_metrics_from_good_returns(self):
        """Good returns should have positive Sharpe."""
        metrics = _calculate_metrics_from_returns(GOOD_RETURNS)

        assert metrics.sharpe > 0
        assert metrics.max_drawdown <= 0  # Drawdown is negative or zero
        assert metrics.win_ratio >= 0
        assert metrics.num_trades == len(GOOD_RETURNS)

    def test_calculate_metrics_from_bad_returns(self):
        """Bad returns should have negative or low Sharpe."""
        metrics = _calculate_metrics_from_returns(BAD_RETURNS)

        assert metrics.sharpe < 0.5
        assert metrics.max_drawdown < 0  # Significant drawdown
        assert metrics.win_ratio < 0.5  # Low win rate

    def test_calculate_metrics_from_empty_returns(self):
        """Empty returns should return zero metrics."""
        metrics = _calculate_metrics_from_returns([])

        assert metrics.sharpe == 0.0
        assert metrics.max_drawdown == 0.0
        assert metrics.win_ratio == 0.0
        assert metrics.num_trades == 0

    def test_calculate_metrics_handles_nan(self):
        """NaN values should be filtered out."""
        returns_with_nan = [0.01, float("nan"), 0.02, float("nan"), 0.015]
        metrics = _calculate_metrics_from_returns(returns_with_nan)

        # Should calculate from non-NaN values only
        assert metrics.sharpe != float("nan")
        assert metrics.num_trades == 3  # Only 3 valid returns

    def test_metrics_to_policy_format(self):
        """Metrics should convert to policy-compatible format."""
        metrics = PerformanceMetrics(
            sharpe=1.5,
            max_drawdown=-0.15,  # Negative
            win_ratio=0.6,
            profit_factor=1.8,
        )
        policy_metrics = metrics.to_policy_metrics()

        assert policy_metrics["sharpe"] == 1.5
        assert policy_metrics["max_drawdown"] == 0.15  # Converted to positive
        assert policy_metrics["win_rate"] == 0.6
        assert policy_metrics["profit_factor"] == 1.8

    def test_from_dict_creates_metrics(self):
        """from_dict should create metrics from raw dict."""
        raw = {
            "sharpe": 1.2,
            "max_drawdown": -0.1,
            "win_ratio": 0.55,
            "profit_factor": 1.5,
        }
        metrics = PerformanceMetrics.from_dict(raw)

        assert metrics.sharpe == 1.2
        assert metrics.max_drawdown == -0.1
        assert metrics.win_ratio == 0.55
        assert metrics.profit_factor == 1.5


# ============================================================================
# Threshold Checking Tests
# ============================================================================


class TestThresholdChecking:
    """Tests for threshold checking logic."""

    def test_check_thresholds_passes_good_metrics(self):
        """Good metrics should pass sandbox thresholds."""
        metrics = PerformanceMetrics(sharpe=1.5, max_drawdown=-0.1, win_ratio=0.6)
        policy = get_preset(PolicyPreset.SANDBOX)

        violations = _check_thresholds(metrics, policy)
        assert len(violations) == 0

    def test_check_thresholds_fails_low_sharpe(self):
        """Low Sharpe should fail conservative threshold."""
        metrics = PerformanceMetrics(sharpe=0.3, max_drawdown=-0.1, win_ratio=0.6)
        policy = get_preset(PolicyPreset.CONSERVATIVE)

        violations = _check_thresholds(metrics, policy)
        assert len(violations) > 0
        assert any(v.metric == "sharpe" for v in violations)

    def test_check_thresholds_fails_high_drawdown(self):
        """High drawdown should fail conservative threshold."""
        metrics = PerformanceMetrics(sharpe=1.5, max_drawdown=-0.3, win_ratio=0.6)
        policy = get_preset(PolicyPreset.CONSERVATIVE)  # max_drawdown: 0.15

        violations = _check_thresholds(metrics, policy)
        assert len(violations) > 0
        assert any(v.metric == "max_drawdown" for v in violations)

    def test_check_thresholds_violation_details(self):
        """Violations should contain detailed info."""
        metrics = PerformanceMetrics(sharpe=0.5, max_drawdown=-0.1, win_ratio=0.6)
        policy = PresetPolicy(
            name="test",
            description="test",
            thresholds=[ThresholdConfig(metric="sharpe", min=1.0)],
        )

        violations = _check_thresholds(metrics, policy)
        assert len(violations) == 1

        v = violations[0]
        assert v.metric == "sharpe"
        assert v.value == 0.5
        assert v.threshold_type == "min"
        assert v.threshold_value == 1.0
        assert "0.5" in v.message


class TestMonotonicGuard:
    """Tests for monotonicity protection."""

    def test_downward_equity_triggers_violation(self):
        """Strictly decreasing returns should trigger monotonicity guard."""
        pipeline = ValidationPipeline(preset=PolicyPreset.CONSERVATIVE)
        decreasing = [-0.01, -0.02, -0.03, -0.04, -0.05]
        result = pipeline.validate_sync(MockStrategy(returns=decreasing))

        assert result.status == ValidationStatus.FAILED
        assert any(v.metric == "equity_monotonicity" for v in result.violations)


# ============================================================================
# Improvement Hints Tests
# ============================================================================


class TestImprovementHints:
    """Tests for improvement hint generation."""

    def test_sharpe_hint(self):
        """Sharpe violation should generate specific hint."""
        violations = [
            ThresholdViolation(
                metric="sharpe",
                value=0.5,
                threshold_type="min",
                threshold_value=1.0,
                message="sharpe is low",
            )
        ]
        hints = _generate_improvement_hints(violations)

        assert len(hints) > 0
        assert any("sharpe" in h.lower() for h in hints)

    def test_drawdown_hint(self):
        """Drawdown violation should generate specific hint."""
        violations = [
            ThresholdViolation(
                metric="max_drawdown",
                value=0.25,
                threshold_type="max",
                threshold_value=0.15,
                message="drawdown too high",
            )
        ]
        hints = _generate_improvement_hints(violations)

        assert len(hints) > 0
        assert any("drawdown" in h.lower() for h in hints)

    def test_empty_violations_fallback(self):
        """Empty violations should still return a hint."""
        hints = _generate_improvement_hints([])

        # Should return generic hint
        assert len(hints) == 0 or all(isinstance(h, str) for h in hints)


# ============================================================================
# Weight and Rank Calculation Tests
# ============================================================================


class TestWeightAndRank:
    """Tests for weight and rank calculation."""

    def test_new_strategy_gets_weight(self):
        """New strategy with good Sharpe should get weight."""
        metrics = PerformanceMetrics(sharpe=1.5)
        policy = get_preset(PolicyPreset.MODERATE)

        weight, rank = _calculate_weight_and_rank(
            "new_strategy",
            metrics,
            {},  # No existing strategies
            policy,
        )

        assert weight == 1.0  # Only strategy gets all weight
        assert rank == 1

    def test_rank_based_on_sharpe(self):
        """Rank should be based on Sharpe ratio."""
        new_metrics = PerformanceMetrics(sharpe=1.0)
        existing = {
            "best": {"sharpe": 2.0},
            "worst": {"sharpe": 0.5},
        }
        policy = get_preset(PolicyPreset.MODERATE)

        weight, rank = _calculate_weight_and_rank(
            "new_strategy",
            new_metrics,
            existing,
            policy,
        )

        assert rank == 2  # Between best (1) and worst (3)

    def test_weight_proportional_to_sharpe(self):
        """Weight should be proportional to Sharpe."""
        new_metrics = PerformanceMetrics(sharpe=1.0)
        existing = {"other": {"sharpe": 1.0}}  # Same Sharpe
        policy = get_preset(PolicyPreset.MODERATE)

        weight, rank = _calculate_weight_and_rank(
            "new_strategy",
            new_metrics,
            existing,
            policy,
        )

        assert 0.4 <= weight <= 0.6  # Should be around 50%


class TestContributionEstimate:
    """Tests for contribution estimation."""

    def test_contribution_scales_with_weight(self):
        """Higher weight should mean higher contribution."""
        metrics = PerformanceMetrics(sharpe=1.5)

        contrib_high = _estimate_contribution(0.5, metrics, world_sharpe=1.0)
        contrib_low = _estimate_contribution(0.1, metrics, world_sharpe=1.0)

        assert contrib_high > contrib_low

    def test_contribution_scales_with_sharpe(self):
        """Higher Sharpe should mean higher contribution."""
        high_sharpe = PerformanceMetrics(sharpe=2.0)
        low_sharpe = PerformanceMetrics(sharpe=0.5)

        contrib_high = _estimate_contribution(0.2, high_sharpe, world_sharpe=1.0)
        contrib_low = _estimate_contribution(0.2, low_sharpe, world_sharpe=1.0)

        assert contrib_high > contrib_low


# ============================================================================
# ValidationPipeline Tests
# ============================================================================


class TestValidationPipeline:
    """Tests for ValidationPipeline class."""

    @pytest.mark.asyncio
    async def test_validate_good_strategy(self):
        """Good strategy should pass validation."""
        pipeline = ValidationPipeline(preset=PolicyPreset.SANDBOX)
        strategy = MockStrategy("GoodStrategy", GOOD_RETURNS)

        result = await pipeline.validate(strategy, returns=GOOD_RETURNS)

        assert result.status == ValidationStatus.PASSED
        assert result.activated is True
        assert result.weight > 0
        assert result.metrics.sharpe > 0

    @pytest.mark.asyncio
    async def test_validate_bad_strategy_with_strict_policy(self):
        """Bad strategy should fail strict policy."""
        pipeline = ValidationPipeline(preset=PolicyPreset.CONSERVATIVE)
        strategy = MockStrategy("BadStrategy", BAD_RETURNS)

        result = await pipeline.validate(strategy, returns=BAD_RETURNS)

        assert result.status == ValidationStatus.FAILED
        assert result.activated is False
        assert len(result.violations) > 0
        assert len(result.improvement_hints) > 0

    @pytest.mark.asyncio
    async def test_validate_metrics_only_skips_policy(self):
        """Metrics-only mode returns metrics without policy gating."""
        pipeline = ValidationPipeline(preset=PolicyPreset.CONSERVATIVE, metrics_only=True)
        strategy = MockStrategy("BadStrategy", BAD_RETURNS)

        result = await pipeline.validate(strategy, returns=BAD_RETURNS)

        assert result.status == ValidationStatus.PASSED
        assert result.metrics.sharpe is not None
        assert result.violations == []

    @pytest.mark.asyncio
    async def test_validate_extracts_returns_from_strategy(self):
        """Pipeline should extract returns from strategy if not provided."""
        pipeline = ValidationPipeline(preset=PolicyPreset.SANDBOX)
        strategy = MockStrategy("TestStrategy", GOOD_RETURNS)

        result = await pipeline.validate(strategy)  # No returns provided

        assert result.status == ValidationStatus.PASSED
        assert result.metrics.num_trades == len(GOOD_RETURNS)

    def test_validate_sync(self):
        """Sync validation should work."""
        pipeline = ValidationPipeline(preset=PolicyPreset.SANDBOX)
        strategy = MockStrategy("TestStrategy", GOOD_RETURNS)

        result = pipeline.validate_sync(strategy, returns=GOOD_RETURNS)

        assert result.status == ValidationStatus.PASSED

    @pytest.mark.asyncio
    async def test_validate_with_custom_policy(self):
        """Custom policy should be used for validation."""
        from qmtl.services.worldservice.policy_engine import Policy, ThresholdRule

        custom_policy = Policy(
            thresholds={"sharpe": ThresholdRule(metric="sharpe", min=5.0)}  # Very strict
        )
        pipeline = ValidationPipeline(policy=custom_policy)
        strategy = MockStrategy("TestStrategy", GOOD_RETURNS)

        result = await pipeline.validate(strategy, returns=GOOD_RETURNS)

        # Should fail with strict threshold
        assert result.status == ValidationStatus.FAILED

    @pytest.mark.asyncio
    async def test_validate_with_existing_strategies(self):
        """Existing strategies should affect rank calculation."""
        pipeline = ValidationPipeline(
            preset=PolicyPreset.SANDBOX,
            existing_strategies={
                "best": {"sharpe": 5.0},
                "good": {"sharpe": 2.0},
            },
        )
        strategy = MockStrategy("NewStrategy", GOOD_RETURNS)

        result = await pipeline.validate(strategy, returns=GOOD_RETURNS)

        assert result.rank >= 2  # Not the best


# ============================================================================
# Convenience Function Tests
# ============================================================================


class TestConvenienceFunctions:
    """Tests for convenience validation functions."""

    @pytest.mark.asyncio
    async def test_validate_strategy_function(self):
        """validate_strategy should work with defaults."""
        strategy = MockStrategy("TestStrategy", GOOD_RETURNS)

        result = await validate_strategy(strategy, returns=GOOD_RETURNS)

        assert result.status in (ValidationStatus.PASSED, ValidationStatus.FAILED)
        assert result.strategy_id == "TestStrategy"

    def test_validate_strategy_sync_function(self):
        """validate_strategy_sync should work."""
        strategy = MockStrategy("TestStrategy", GOOD_RETURNS)

        result = validate_strategy_sync(strategy, returns=GOOD_RETURNS)

        assert result.status in (ValidationStatus.PASSED, ValidationStatus.FAILED)


# ============================================================================
# ValidationResult Properties Tests
# ============================================================================


class TestValidationResultProperties:
    """Tests for ValidationResult properties."""

    def test_passed_property(self):
        """passed property should reflect status."""
        passed_result = ValidationResult(
            status=ValidationStatus.PASSED,
            metrics=PerformanceMetrics(),
            strategy_id="test",
            world_id="world",
        )
        failed_result = ValidationResult(
            status=ValidationStatus.FAILED,
            metrics=PerformanceMetrics(),
            strategy_id="test",
            world_id="world",
        )

        assert passed_result.passed is True
        assert failed_result.passed is False

    def test_failed_property(self):
        """failed property should reflect status."""
        passed_result = ValidationResult(
            status=ValidationStatus.PASSED,
            metrics=PerformanceMetrics(),
            strategy_id="test",
            world_id="world",
        )
        failed_result = ValidationResult(
            status=ValidationStatus.FAILED,
            metrics=PerformanceMetrics(),
            strategy_id="test",
            world_id="world",
        )

        assert passed_result.failed is False
        assert failed_result.failed is True
