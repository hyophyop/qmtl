"""Tests for the SDK validation/metrics pipeline.

WorldService is the SSOT for policy/rule evaluation. These tests assert that the
SDK-side pipeline computes metrics and does not gate/activate locally.
"""

from __future__ import annotations

import pytest

from qmtl.runtime.sdk.validation_pipeline import (
    ValidationPipeline,
    ValidationResult,
    ValidationStatus,
    PerformanceMetrics,
    calculate_performance_metrics,
    validate_strategy,
    validate_strategy_sync,
)

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
        metrics = calculate_performance_metrics(GOOD_RETURNS)

        assert metrics.sharpe > 0
        assert metrics.max_drawdown <= 0  # Drawdown is negative or zero
        assert metrics.win_ratio >= 0
        assert metrics.num_trades == len(GOOD_RETURNS)

    def test_calculate_metrics_from_bad_returns(self):
        """Bad returns should have negative or low Sharpe."""
        metrics = calculate_performance_metrics(BAD_RETURNS)

        assert metrics.sharpe < 0.5
        assert metrics.max_drawdown < 0  # Significant drawdown
        assert metrics.win_ratio < 0.5  # Low win rate

    def test_calculate_metrics_from_empty_returns(self):
        """Empty returns should return zero metrics."""
        metrics = calculate_performance_metrics([])

        assert metrics.sharpe == 0.0
        assert metrics.max_drawdown == 0.0
        assert metrics.win_ratio == 0.0
        assert metrics.num_trades == 0

    def test_calculate_metrics_handles_nan(self):
        """NaN values should be filtered out."""
        returns_with_nan = [0.01, float("nan"), 0.02, float("nan"), 0.015]
        metrics = calculate_performance_metrics(returns_with_nan)

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
# ValidationPipeline Tests
# ============================================================================


class TestValidationPipeline:
    """Tests for ValidationPipeline class."""

    @pytest.mark.asyncio
    async def test_validate_good_strategy(self):
        """ValidationPipeline should compute metrics without gating."""
        pipeline = ValidationPipeline()
        strategy = MockStrategy("GoodStrategy", GOOD_RETURNS)

        result = await pipeline.validate(strategy, returns=GOOD_RETURNS)

        assert result.status == ValidationStatus.PASSED
        assert result.activated is False
        assert result.weight == 0.0
        assert result.metrics.sharpe > 0

    @pytest.mark.asyncio
    async def test_validate_empty_returns_errors(self):
        pipeline = ValidationPipeline()
        strategy = MockStrategy("EmptyStrategy", [])
        result = await pipeline.validate(strategy, returns=[])
        assert result.status == ValidationStatus.ERROR

    @pytest.mark.asyncio
    async def test_validate_extracts_returns_from_strategy(self):
        """Pipeline should extract returns from strategy if not provided."""
        pipeline = ValidationPipeline()
        strategy = MockStrategy("TestStrategy", GOOD_RETURNS)

        result = await pipeline.validate(strategy)  # No returns provided

        assert result.status == ValidationStatus.PASSED
        assert result.metrics.num_trades == len(GOOD_RETURNS)

    def test_validate_sync(self):
        """Sync validation should work."""
        pipeline = ValidationPipeline()
        strategy = MockStrategy("TestStrategy", GOOD_RETURNS)

        result = pipeline.validate_sync(strategy, returns=GOOD_RETURNS)

        assert result.status == ValidationStatus.PASSED


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

        assert result.status == ValidationStatus.PASSED
        assert result.strategy_id == "TestStrategy"

    def test_validate_strategy_sync_function(self):
        """validate_strategy_sync should work."""
        strategy = MockStrategy("TestStrategy", GOOD_RETURNS)

        result = validate_strategy_sync(strategy, returns=GOOD_RETURNS)

        assert result.status == ValidationStatus.PASSED


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
