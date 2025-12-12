"""Good/Bad/Borderline strategy scenario tests.

These tests verify that validation rules correctly classify different strategy profiles:
- Good: Stable Sharpe, adequate sample, good tail/liquidity risk
- Bad: Extreme leverage, too short backtest, excessive search intensity
- Borderline: Near threshold values that should trigger warnings

Reference: world_validation_architecture.md §11.2
"""

from __future__ import annotations

import pytest

from qmtl.services.worldservice.policy_engine import (
    Policy,
    ValidationProfile,
    SampleProfile,
    PerformanceProfile,
    RobustnessProfile,
    RiskProfile,
    evaluate_policy,
    parse_policy,
)


# =============================================================================
# STRATEGY SCENARIO FIXTURES
# =============================================================================


def _good_strategy_metrics() -> dict[str, float]:
    """A 'good' strategy with stable performance and adequate sample."""
    return {
        # Returns metrics
        "sharpe": 1.2,
        "max_drawdown": 0.15,
        "gain_to_pain_ratio": 1.8,
        "time_under_water_ratio": 0.2,
        # Sample metrics
        "effective_history_years": 5.0,
        "n_trades_total": 500,
        "n_trades_per_year": 100.0,
        # Risk metrics
        "adv_utilization_p95": 0.1,
        "participation_rate_p95": 0.05,
        # Robustness metrics
        "deflated_sharpe_ratio": 0.8,
        "sharpe_first_half": 1.1,
        "sharpe_second_half": 1.3,
        # Diagnostics
        "strategy_complexity": 3.0,
        "search_intensity": 10,
    }


def _bad_strategy_short_history() -> dict[str, float]:
    """A 'bad' strategy with insufficient sample size."""
    return {
        "sharpe": 2.5,  # Suspiciously high
        "max_drawdown": 0.05,
        "gain_to_pain_ratio": 3.0,
        "time_under_water_ratio": 0.1,
        "effective_history_years": 0.5,  # Too short
        "n_trades_total": 20,  # Too few trades
        "n_trades_per_year": 40.0,
        "adv_utilization_p95": 0.05,
        "participation_rate_p95": 0.02,
        "deflated_sharpe_ratio": 0.3,  # Low DSR due to short history
        "sharpe_first_half": 2.8,
        "sharpe_second_half": 2.2,
        "strategy_complexity": 8.0,  # High complexity
        "search_intensity": 500,  # Excessive search
    }


def _bad_strategy_high_risk() -> dict[str, float]:
    """A 'bad' strategy with excessive risk metrics."""
    return {
        "sharpe": 0.9,
        "max_drawdown": 0.45,  # Too high
        "gain_to_pain_ratio": 0.8,  # Below 1.0
        "time_under_water_ratio": 0.6,
        "effective_history_years": 3.0,
        "n_trades_total": 200,
        "n_trades_per_year": 67.0,
        "adv_utilization_p95": 0.5,  # Too high
        "participation_rate_p95": 0.4,  # Too high
        "deflated_sharpe_ratio": 0.5,
        "sharpe_first_half": 1.2,
        "sharpe_second_half": 0.6,  # Large gap
        "strategy_complexity": 5.0,
        "search_intensity": 50,
    }


def _bad_strategy_low_sharpe() -> dict[str, float]:
    """A 'bad' strategy with poor performance metrics."""
    return {
        "sharpe": 0.3,  # Too low
        "max_drawdown": 0.25,
        "gain_to_pain_ratio": 0.9,  # Below 1.0
        "time_under_water_ratio": 0.4,
        "effective_history_years": 4.0,
        "n_trades_total": 300,
        "n_trades_per_year": 75.0,
        "adv_utilization_p95": 0.15,
        "participation_rate_p95": 0.1,
        "deflated_sharpe_ratio": 0.15,  # Very low
        "sharpe_first_half": 0.4,
        "sharpe_second_half": 0.2,
        "strategy_complexity": 2.0,
        "search_intensity": 20,
    }


def _borderline_strategy() -> dict[str, float]:
    """A 'borderline' strategy near threshold values."""
    return {
        "sharpe": 0.81,  # Just above 0.8 threshold
        "max_drawdown": 0.24,  # Just below 0.25 threshold
        "gain_to_pain_ratio": 1.21,  # Just above 1.2 threshold
        "time_under_water_ratio": 0.35,
        "effective_history_years": 3.01,  # Just above 3.0 threshold
        "n_trades_total": 201,  # Just above 200 threshold
        "n_trades_per_year": 67.0,
        "adv_utilization_p95": 0.29,  # Just below 0.3 threshold
        "participation_rate_p95": 0.19,  # Just below 0.2 threshold
        "deflated_sharpe_ratio": 0.31,  # Just above 0.3 threshold
        "sharpe_first_half": 0.9,
        "sharpe_second_half": 0.7,  # Gap of 0.2
        "strategy_complexity": 4.0,
        "search_intensity": 30,
    }


def _v1_paper_policy() -> Policy:
    """Standard v1 paper validation profile policy."""
    return parse_policy(
        """
        validation_profiles:
          paper:
            sample:
              min_effective_years: 3.0
              min_trades_total: 200
            performance:
              sharpe_min: 0.8
              max_dd_max: 0.25
              gain_to_pain_min: 1.2
            robustness:
              dsr_min: 0.3
            risk:
              adv_utilization_p95_max: 0.3
              participation_rate_p95_max: 0.2
        default_profile_by_stage:
          paper_only: paper
        """
    )


# =============================================================================
# GOOD STRATEGY TESTS
# =============================================================================


class TestGoodStrategyScenarios:
    """Tests for strategies that should pass all validation rules."""

    def test_good_strategy_passes_all_rules(self) -> None:
        policy = _v1_paper_policy()
        metrics = {"good_strategy": _good_strategy_metrics()}

        result = evaluate_policy(metrics, policy, stage="paper")

        assert "good_strategy" in result.selected
        rules = result.rule_results["good_strategy"]

        # All core rules should pass
        assert rules["data_currency"].status == "pass"
        assert rules["sample"].status == "pass"
        assert rules["performance"].status == "pass"
        assert rules["robustness"].status == "pass"

    def test_good_strategy_recommended_stage_is_paper(self) -> None:
        policy = _v1_paper_policy()
        metrics = {"good_strategy": _good_strategy_metrics()}

        result = evaluate_policy(metrics, policy, stage="paper")

        assert result.recommended_stage == "paper_only"


# =============================================================================
# BAD STRATEGY TESTS
# =============================================================================


class TestBadStrategyScenarios:
    """Tests for strategies that should fail validation rules."""

    def test_short_history_strategy_fails_sample_rule(self) -> None:
        policy = _v1_paper_policy()
        metrics = {"bad_strategy": _bad_strategy_short_history()}

        result = evaluate_policy(metrics, policy, stage="paper")

        assert "bad_strategy" not in result.selected
        rules = result.rule_results["bad_strategy"]
        assert rules["sample"].status == "fail"
        assert "sample" in rules["sample"].tags

    def test_high_risk_strategy_fails_performance_rule(self) -> None:
        policy = _v1_paper_policy()
        metrics = {"bad_strategy": _bad_strategy_high_risk()}

        result = evaluate_policy(metrics, policy, stage="paper")

        assert "bad_strategy" not in result.selected
        rules = result.rule_results["bad_strategy"]
        # Should fail on max_drawdown or gain_to_pain
        assert rules["performance"].status == "fail"

    def test_low_sharpe_strategy_fails_performance_rule(self) -> None:
        policy = _v1_paper_policy()
        metrics = {"bad_strategy": _bad_strategy_low_sharpe()}

        result = evaluate_policy(metrics, policy, stage="paper")

        assert "bad_strategy" not in result.selected
        rules = result.rule_results["bad_strategy"]
        assert rules["performance"].status == "fail"
        assert "sharpe" in rules["performance"].reason.lower()

    def test_bad_strategies_produce_meaningful_failure_reasons(self) -> None:
        """Verify that failure reasons are human-readable and actionable."""
        policy = _v1_paper_policy()
        bad_strategies = {
            "short_history": _bad_strategy_short_history(),
            "high_risk": _bad_strategy_high_risk(),
            "low_sharpe": _bad_strategy_low_sharpe(),
        }

        result = evaluate_policy(bad_strategies, policy, stage="paper")

        for strategy_id in bad_strategies:
            rules = result.rule_results[strategy_id]
            # At least one rule should fail with a non-empty reason
            failed_rules = [r for r in rules.values() if r.status == "fail"]
            assert len(failed_rules) > 0, f"{strategy_id} should have at least one failing rule"
            for rule in failed_rules:
                assert rule.reason, f"Failed rule should have a reason"
                assert rule.reason_code, f"Failed rule should have a reason_code"


# =============================================================================
# BORDERLINE STRATEGY TESTS
# =============================================================================


class TestBorderlineStrategyScenarios:
    """Tests for strategies near threshold values."""

    def test_borderline_strategy_passes_when_just_above_thresholds(self) -> None:
        policy = _v1_paper_policy()
        metrics = {"borderline": _borderline_strategy()}

        result = evaluate_policy(metrics, policy, stage="paper")

        # Should pass since all values are just above/below thresholds
        assert "borderline" in result.selected

    def test_borderline_strategy_fails_when_slightly_below_threshold(self) -> None:
        policy = _v1_paper_policy()
        borderline = _borderline_strategy()
        borderline["sharpe"] = 0.79  # Just below 0.8 threshold

        result = evaluate_policy({"borderline": borderline}, policy, stage="paper")

        assert "borderline" not in result.selected
        rules = result.rule_results["borderline"]
        assert rules["performance"].status == "fail"

    def test_multiple_borderline_values_all_checked(self) -> None:
        """Verify that all threshold checks are performed even for borderline cases."""
        policy = _v1_paper_policy()
        borderline = _borderline_strategy()

        result = evaluate_policy({"borderline": borderline}, policy, stage="paper")

        rules = result.rule_results["borderline"]
        # All rules should have been evaluated
        assert "data_currency" in rules
        assert "sample" in rules
        assert "performance" in rules
        assert "robustness" in rules
        assert "risk_constraint" in rules


# =============================================================================
# MIXED SCENARIO TESTS
# =============================================================================


class TestMixedScenarios:
    """Tests with multiple strategies of different quality levels."""

    def test_mixed_strategies_correct_selection(self) -> None:
        """Good strategies selected, bad strategies rejected."""
        policy = _v1_paper_policy()
        metrics = {
            "good": _good_strategy_metrics(),
            "bad_short": _bad_strategy_short_history(),
            "bad_risk": _bad_strategy_high_risk(),
            "borderline": _borderline_strategy(),
        }

        result = evaluate_policy(metrics, policy, stage="paper")

        assert "good" in result.selected
        assert "borderline" in result.selected
        assert "bad_short" not in result.selected
        assert "bad_risk" not in result.selected

    def test_rule_results_available_for_all_strategies(self) -> None:
        """Rule results should be available even for rejected strategies."""
        policy = _v1_paper_policy()
        metrics = {
            "good": _good_strategy_metrics(),
            "bad": _bad_strategy_low_sharpe(),
        }

        result = evaluate_policy(metrics, policy, stage="paper")

        # Both strategies should have rule results
        assert "good" in result.rule_results
        assert "bad" in result.rule_results

        # Both should have all core rules evaluated
        for strategy_id in metrics:
            rules = result.rule_results[strategy_id]
            assert "data_currency" in rules
            assert "sample" in rules
            assert "performance" in rules
            assert "robustness" in rules


# =============================================================================
# REGRESSION TEST SET
# =============================================================================


class TestRegressionScenarios:
    """Regression tests to catch unintended policy changes.
    
    These tests use fixed metric values and expected outcomes.
    If a policy change causes these to fail, it should be reviewed.
    """

    @pytest.fixture
    def regression_policy(self) -> Policy:
        """Fixed policy for regression testing."""
        return parse_policy(
            """
            validation_profiles:
              backtest:
                sample:
                  min_effective_years: 2.0
                  min_trades_total: 100
                performance:
                  sharpe_min: 0.5
                  max_dd_max: 0.30
                  gain_to_pain_min: 1.0
                robustness:
                  dsr_min: 0.2
                risk:
                  adv_utilization_p95_max: 0.4
                  participation_rate_p95_max: 0.3
            default_profile_by_stage:
              backtest_only: backtest
            """
        )

    def test_regression_good_strategy_selected(self, regression_policy: Policy) -> None:
        """Fixed good strategy should always be selected."""
        metrics = {
            "regression_good": {
                "sharpe": 1.0,
                "max_drawdown": 0.20,
                "gain_to_pain_ratio": 1.5,
                "effective_history_years": 3.0,
                "n_trades_total": 200,
                "deflated_sharpe_ratio": 0.5,
                "adv_utilization_p95": 0.2,
                "participation_rate_p95": 0.15,
            }
        }

        result = evaluate_policy(metrics, regression_policy, stage="backtest")

        assert "regression_good" in result.selected
        assert result.recommended_stage == "backtest_only"

    def test_regression_bad_strategy_rejected(self, regression_policy: Policy) -> None:
        """Fixed bad strategy should always be rejected."""
        metrics = {
            "regression_bad": {
                "sharpe": 0.3,  # Below 0.5 threshold
                "max_drawdown": 0.35,  # Above 0.30 threshold
                "gain_to_pain_ratio": 0.8,  # Below 1.0 threshold
                "effective_history_years": 1.0,  # Below 2.0 threshold
                "n_trades_total": 50,  # Below 100 threshold
                "deflated_sharpe_ratio": 0.1,  # Below 0.2 threshold
                "adv_utilization_p95": 0.5,  # Above 0.4 threshold
                "participation_rate_p95": 0.4,  # Above 0.3 threshold
            }
        }

        result = evaluate_policy(metrics, regression_policy, stage="backtest")

        assert "regression_bad" not in result.selected

    def test_regression_failure_count_stability(self, regression_policy: Policy) -> None:
        """Bad strategy should fail a consistent number of rules."""
        metrics = {
            "regression_bad": {
                "sharpe": 0.3,
                "max_drawdown": 0.35,
                "gain_to_pain_ratio": 0.8,
                "effective_history_years": 1.0,
                "n_trades_total": 50,
                "deflated_sharpe_ratio": 0.1,
                "adv_utilization_p95": 0.5,
                "participation_rate_p95": 0.4,
            }
        }

        result = evaluate_policy(metrics, regression_policy, stage="backtest")

        rules = result.rule_results["regression_bad"]
        failed_count = sum(1 for r in rules.values() if r.status == "fail")

        # This bad strategy should fail at least 2 rules (sample + performance)
        assert failed_count >= 2, f"Expected at least 2 failures, got {failed_count}"
