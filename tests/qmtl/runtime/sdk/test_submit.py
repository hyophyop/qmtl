"""Tests for QMTL v2.0 submit API."""

from __future__ import annotations

import pytest

from qmtl.runtime.sdk import Mode, Runner, Strategy, StrategyMetrics, SubmitResult
from qmtl.services.worldservice.shared_schemas import ActivationEnvelope, DecisionEnvelope

from qmtl.runtime.sdk.submit import (
    AutoReturnsConfig,
    PrecheckResult,
    WsEvalResult,
    _build_submit_result_from_validation,
    _derive_returns_with_auto,
    submit,
    submit_async,
)
from qmtl.runtime.sdk.validation_pipeline import ValidationStatus

# Suppress noisy resource warnings from http client sockets/event loops in local tests
pytestmark = [
    pytest.mark.filterwarnings("ignore:unclosed.*ResourceWarning"),
    pytest.mark.filterwarnings("ignore:.*unclosed event loop.*ResourceWarning"),
    pytest.mark.filterwarnings("ignore:unclosed <socket.*ResourceWarning"),
]


class SimpleStrategy(Strategy):
    """Minimal test strategy."""

    def setup(self):
        pass


class StrategyWithReturns(Strategy):
    """Strategy with returns for validation testing."""

    def setup(self):
        pass

    @property
    def returns(self):
        return [0.01, 0.02, -0.005, 0.015, 0.012, 0.008, -0.003, 0.02, 0.01, 0.005]


class StrategyWithPrices(Strategy):
    """Strategy that exposes prices but no returns/equity/pnl."""

    def setup(self):
        self.prices = [100.0, 101.0, 99.0, 102.0]


class TestAutoReturns:
    def test_derives_from_prices_when_enabled(self):
        strategy = StrategyWithPrices()
        strategy.setup()

        derived, hints = _derive_returns_with_auto(strategy, AutoReturnsConfig())

        assert derived == pytest.approx([0.01, -0.01980198, 0.03030303])
        assert hints == []

    def test_reports_hint_when_prices_missing(self):
        class NoPricesStrategy(Strategy):
            def setup(self):
                pass

        strategy = NoPricesStrategy()
        strategy.setup()

        derived, hints = _derive_returns_with_auto(strategy, AutoReturnsConfig())

        assert derived == []
        assert any("auto_returns enabled" in hint for hint in hints)


class TestMode:
    """Tests for Mode enum."""

    def test_mode_values(self):
        assert Mode.BACKTEST == "backtest"
        assert Mode.PAPER == "paper"
        assert Mode.LIVE == "live"

    def test_mode_from_string(self):
        assert Mode("backtest") == Mode.BACKTEST
        assert Mode("paper") == Mode.PAPER
        assert Mode("live") == Mode.LIVE

    def test_invalid_mode(self):
        with pytest.raises(ValueError):
            Mode("invalid")


class TestSubmitResult:
    """Tests for SubmitResult dataclass."""

    def test_minimal_result(self):
        result = SubmitResult(
            strategy_id="s1",
            status="pending",
            world="test",
            mode=Mode.BACKTEST,
        )
        assert result.strategy_id == "s1"
        assert result.status == "pending"
        assert result.world == "test"
        assert result.mode == Mode.BACKTEST
        assert result.contribution is None
        assert result.weight is None
        assert result.rank is None
        assert result.downgraded is False
        assert result.downgrade_reason is None
        assert result.safe_mode is False

    def test_full_result(self):
        result = SubmitResult(
            strategy_id="s1",
            status="active",
            world="prod",
            mode=Mode.LIVE,
            contribution=0.05,
            weight=0.1,
            rank=3,
            metrics=StrategyMetrics(sharpe=1.5, max_drawdown=0.1),
        )
        assert result.contribution == 0.05
        assert result.weight == 0.1
        assert result.rank == 3
        assert result.metrics.sharpe == 1.5
        assert result.metrics.max_drawdown == 0.1

    def test_rejected_result(self):
        result = SubmitResult(
            strategy_id="s1",
            status="rejected",
            world="test",
            mode=Mode.PAPER,
            rejection_reason="Policy threshold not met",
            improvement_hints=["Increase sharpe ratio above 1.0"],
        )
        assert result.status == "rejected"
        assert result.rejection_reason == "Policy threshold not met"
        assert len(result.improvement_hints) == 1
        assert result.downgraded is False
        assert result.safe_mode is False

    def test_submit_result_embeds_envelopes(self):
        decision = DecisionEnvelope(
            world_id="world-1",
            policy_version=3,
            effective_mode="validate",
            as_of="2024-01-01T00:00:00Z",
            ttl="300s",
            etag="etag-1",
        )
        activation = ActivationEnvelope(
            world_id="world-1",
            strategy_id="strat-1",
            side="long",
            active=True,
            weight=0.15,
            etag="etag-activation",
            ts="2024-01-01T00:05:00Z",
        )

        result = SubmitResult(
            strategy_id="placeholder",
            status="active",
            world="placeholder-world",
            mode=Mode.LIVE,
            decision=decision,
            activation=activation,
        )

        assert result.world == decision.world_id == activation.world_id
        assert result.strategy_id == activation.strategy_id
        assert result.weight == activation.weight
        assert result.downgraded is False

    def test_submit_result_downgrade_flags(self):
        result = SubmitResult(
            strategy_id="s2",
            status="pending",
            world="w",
            mode=Mode.BACKTEST,
            downgraded=True,
            downgrade_reason="missing_as_of",
            safe_mode=True,
        )

        assert result.downgraded is True
        assert result.downgrade_reason == "missing_as_of"
        assert result.safe_mode is True

    def test_submit_requires_nonempty_world(self):
        with pytest.raises(ValueError):
            submit(SimpleStrategy, world="   ")

    def test_ws_eval_overrides_validation_fields_and_preserves_precheck(self):
        class DummyMetrics:
            sharpe = 1.0
            max_drawdown = 0.1
            win_ratio = 0.6
            profit_factor = 1.2
            car_mdd = 0.0
            rar_mdd = 0.0
            total_return = 0.05
            num_trades = 10
            correlation_avg = 0.3

        class DummyValidation:
            def __init__(self):
                self.status = ValidationStatus.PASSED
                self.weight = 0.11
                self.rank = 7
                self.contribution = 0.02
                self.activated = True
                self.metrics = DummyMetrics()
                self.violations = []
                self.improvement_hints = []
                self.correlation_avg = 0.3

        ws_eval = WsEvalResult(
            active=True,
            weight=0.25,
            rank=2,
            contribution=0.08,
            violations=[],
            correlation_avg=0.42,
        )
        validation = DummyValidation()
        strategy = SimpleStrategy()

        result = _build_submit_result_from_validation(
            strategy=strategy,
            strategy_class_name="SimpleStrategy",
            strategy_id="sid-1",
            resolved_world="world-1",
            mode=Mode.BACKTEST,
            world_notice=[],
            validation_result=validation,
            ws_eval=ws_eval,
            gateway_available=True,
        )

        assert result.status == "active"
        assert result.weight == ws_eval.weight
        assert result.rank == ws_eval.rank
        assert result.contribution == ws_eval.contribution
        assert result.metrics.correlation_avg == ws_eval.correlation_avg
        assert result.threshold_violations == ws_eval.violations
        assert result.precheck is not None
        assert result.precheck.status == ValidationStatus.PASSED.value
        assert result.precheck.weight == validation.weight
        assert result.precheck.rank == validation.rank
        assert result.precheck.contribution == validation.contribution
        assert result.precheck.correlation_avg == validation.correlation_avg

    def test_ws_rejection_uses_ws_violations_and_keeps_precheck(self):
        class DummyMetrics:
            sharpe = 0.5
            max_drawdown = 0.2
            win_ratio = 0.4
            profit_factor = 0.9
            car_mdd = 0.0
            rar_mdd = 0.0
            total_return = -0.02
            num_trades = 8
            correlation_avg = 0.1

        class DummyValidation:
            def __init__(self):
                self.status = ValidationStatus.PASSED
                self.weight = 0.05
                self.rank = 9
                self.contribution = 0.0
                self.activated = False
                self.metrics = DummyMetrics()
                self.violations = []
                self.improvement_hints = ["local hint"]
                self.correlation_avg = 0.1

        ws_eval = WsEvalResult(
            active=False,
            violations=[{"metric": "sharpe", "threshold_type": "min", "threshold_value": 1.0, "message": "too low"}],
        )
        validation = DummyValidation()
        strategy = SimpleStrategy()

        result = _build_submit_result_from_validation(
            strategy=strategy,
            strategy_class_name="SimpleStrategy",
            strategy_id="sid-2",
            resolved_world="world-2",
            mode=Mode.BACKTEST,
            world_notice=["notice"],
            validation_result=validation,
            ws_eval=ws_eval,
            gateway_available=True,
        )

        assert result.status == "rejected"
        assert result.threshold_violations == ws_eval.violations
        assert result.improvement_hints  # keeps local hints
        assert result.precheck is not None
        assert result.precheck.status == ValidationStatus.PASSED.value
        assert result.precheck.violations == []

    def test_ws_error_keeps_pending_with_precheck(self):
        class DummyMetrics:
            sharpe = 0.7
            max_drawdown = 0.3
            win_ratio = 0.45
            profit_factor = 1.0
            car_mdd = 0.0
            rar_mdd = 0.0
            total_return = 0.01
            num_trades = 5
            correlation_avg = 0.2

        class DummyViolation:
            def __init__(self):
                self.metric = "sharpe"
                self.value = 0.7
                self.threshold_type = "min"
                self.threshold_value = 1.0
                self.message = "too low"

        class DummyValidation:
            def __init__(self):
                self.status = ValidationStatus.FAILED
                self.weight = 0.0
                self.rank = 0
                self.contribution = 0.0
                self.activated = False
                self.metrics = DummyMetrics()
                self.violations = [DummyViolation()]
                self.improvement_hints = ["local failure"]
                self.correlation_avg = 0.2

        ws_eval = WsEvalResult(
            active=None,
            error="gateway unreachable",
            violations=None,
        )
        validation = DummyValidation()
        strategy = SimpleStrategy()

        result = _build_submit_result_from_validation(
            strategy=strategy,
            strategy_class_name="SimpleStrategy",
            strategy_id="sid-3",
            resolved_world="world-3",
            mode=Mode.BACKTEST,
            world_notice=[],
            validation_result=validation,
            ws_eval=ws_eval,
            gateway_available=True,
        )

        assert result.status == "pending"
        assert result.threshold_violations == [
            {
                "metric": "sharpe",
                "value": 0.7,
                "threshold_type": "min",
                "threshold_value": 1.0,
                "message": "too low",
            }
        ]
        assert result.precheck is not None
        assert result.precheck.status == ValidationStatus.FAILED.value

    def test_submit_result_to_dict_includes_ws_and_precheck(self):
        precheck = PrecheckResult(
            status="passed",
            weight=0.02,
            rank=5,
            contribution=0.01,
            metrics=StrategyMetrics(sharpe=1.1, max_drawdown=0.2),
            violations=[{"metric": "sharpe", "threshold_type": "min", "threshold_value": 1.0}],
            improvement_hints=["hint"],
        )
        result = SubmitResult(
            strategy_id="s3",
            status="active",
            world="w",
            mode=Mode.PAPER,
            contribution=0.05,
            weight=0.1,
            rank=2,
            metrics=StrategyMetrics(sharpe=1.5, max_drawdown=0.1),
            precheck=precheck,
        )

        payload = result.to_dict()
        assert payload["status"] == "active"
        assert payload["mode"] == "paper"
        assert payload["weight"] == 0.1
        assert payload["precheck"]["status"] == "passed"
        assert payload["precheck"]["weight"] == 0.02
        assert "ws" in payload
        assert payload["ws"]["status"] == "active"
        assert payload["ws"]["weight"] == 0.1
        assert payload["ws"]["threshold_violations"] == []

    def test_ws_envelopes_from_eval_propagate_into_result(self):
        class DummyMetrics:
            sharpe = 1.0
            max_drawdown = 0.1
            win_ratio = 0.6
            profit_factor = 1.2
            car_mdd = 0.0
            rar_mdd = 0.0
            total_return = 0.05
            num_trades = 10
            correlation_avg = 0.3

        class DummyValidation:
            def __init__(self):
                self.status = ValidationStatus.PASSED
                self.weight = 0.1
                self.rank = 4
                self.contribution = 0.02
                self.activated = True
                self.metrics = DummyMetrics()
                self.violations = []
                self.improvement_hints = []
                self.correlation_avg = 0.3

        decision = DecisionEnvelope(
            world_id="world-x",
            policy_version=1,
            effective_mode="validate",
            reason="stub",
            as_of="2025-01-01T00:00:00Z",
            ttl="60s",
            etag="etag-dec",
        )
        activation = ActivationEnvelope(
            world_id="world-x",
            strategy_id="sid-x",
            side="long",
            active=True,
            weight=0.33,
            etag="etag-act",
            run_id="run-x",
            ts="2025-01-01T00:00:01Z",
        )
        ws_eval = WsEvalResult(
            active=True,
            weight=0.33,
            rank=1,
            contribution=0.12,
            violations=[],
            correlation_avg=0.45,
            decision=decision,
            activation=activation,
        )
        validation = DummyValidation()
        strategy = SimpleStrategy()

        result = _build_submit_result_from_validation(
            strategy=strategy,
            strategy_class_name="SimpleStrategy",
            strategy_id="sid-x",
            resolved_world="world-x",
            mode=Mode.BACKTEST,
            world_notice=[],
            validation_result=validation,
            ws_eval=ws_eval,
            gateway_available=True,
        )

        assert result.decision is decision
        assert result.activation is activation
        payload = result.to_dict()
        assert payload["ws"]["decision"]["world_id"] == "world-x"
        assert payload["ws"]["activation"]["weight"] == 0.33


class TestSubmitFunction:
    """Tests for submit() function."""

    def test_submit_with_class(self):
        """Test submit with strategy class."""
        result = submit(SimpleStrategy)
        assert isinstance(result, SubmitResult)
        assert result.status in ("pending", "active", "rejected", "error")

    def test_submit_with_instance(self):
        """Test submit with strategy instance."""
        strategy = SimpleStrategy()
        result = submit(strategy)
        assert isinstance(result, SubmitResult)

    def test_submit_with_world(self):
        """Test submit with explicit world."""
        result = submit(SimpleStrategy, world="test_world")
        assert result.world == "test_world"

    def test_submit_with_mode(self):
        """Test submit with explicit mode."""
        result = submit(SimpleStrategy, mode=Mode.PAPER)
        assert result.mode == Mode.PAPER

    def test_submit_backtest_mode(self):
        """Test submit in backtest mode (offline)."""
        result = submit(SimpleStrategy, mode=Mode.BACKTEST)
        assert result.mode == Mode.BACKTEST

    def test_submit_rejects_when_no_returns_available(self):
        """Auto-validate should fail when no returns are produced."""
        class NoReturnsStrategy(Strategy):
            def setup(self):
                pass

        result = submit(NoReturnsStrategy)
        assert result.status == "rejected"
        assert "returns" in (result.rejection_reason or "").lower()

    def test_run_removed(self):
        """Legacy runner helpers are removed; only submit remains."""
        assert not hasattr(Runner, "run")
        assert not hasattr(Runner, "offline")


class TestSubmitAsync:
    """Tests for submit_async() function."""

    @pytest.mark.asyncio
    async def test_submit_async_with_class(self):
        """Test async submit with strategy class."""
        result = await submit_async(SimpleStrategy)
        assert isinstance(result, SubmitResult)

    @pytest.mark.asyncio
    async def test_submit_async_with_mode(self):
        """Test async submit with explicit mode."""
        result = await submit_async(SimpleStrategy, mode=Mode.PAPER)
        assert result.mode == Mode.PAPER


class TestSubmitInRunningLoop:
    """Tests for calling submit from a running event loop."""

    @pytest.mark.asyncio
    async def test_submit_sync_inside_event_loop(self):
        """Runner.submit should work even when an event loop is already running."""
        result = Runner.submit(SimpleStrategy)
        assert isinstance(result, SubmitResult)


class TestSubmitWithValidation:
    """Tests for submit() with validation pipeline (Phase 2)."""

    def test_submit_with_preset(self):
        """Test submit with explicit preset."""
        result = submit(SimpleStrategy, preset="sandbox")
        assert isinstance(result, SubmitResult)

    def test_submit_with_returns(self):
        """Test submit with pre-computed returns."""
        returns = [0.01, 0.02, -0.005, 0.015, 0.012]
        result = submit(SimpleStrategy, returns=returns)
        assert isinstance(result, SubmitResult)

    def test_submit_auto_validate_true(self):
        """Test submit with auto_validate=True (default)."""
        returns = [0.01, 0.02, 0.015, 0.012]
        result = submit(SimpleStrategy, returns=returns, auto_validate=True)
        # Should have validation results
        assert result.status in ("pending", "active", "validated", "rejected")

    def test_submit_auto_validate_false(self):
        """Test submit with auto_validate=False."""
        returns = [0.01, 0.02, 0.015, 0.012]
        result = submit(SimpleStrategy, returns=returns, auto_validate=False)
        # Should skip validation
        assert result.status in ("pending", "active")

    def test_submit_extracts_returns_from_strategy(self):
        """Test that submit extracts returns from strategy with returns property."""
        result = submit(StrategyWithReturns)
        assert isinstance(result, SubmitResult)

    @pytest.mark.asyncio
    async def test_submit_async_with_validation(self):
        """Test async submit with validation parameters."""
        returns = [0.01, 0.02, -0.005, 0.015, 0.012]
        result = await submit_async(
            SimpleStrategy,
            returns=returns,
            preset="conservative",
            auto_validate=True,
        )
        assert isinstance(result, SubmitResult)
        # With conservative preset and these returns, should have metrics
        assert result.metrics is not None
