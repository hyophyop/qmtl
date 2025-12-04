"""Tests for QMTL v2.0 submit API."""

from __future__ import annotations

import pytest

from qmtl.runtime.sdk import Mode, Runner, Strategy, StrategyMetrics, SubmitResult
from qmtl.services.worldservice.shared_schemas import ActivationEnvelope, DecisionEnvelope

from qmtl.runtime.sdk.submit import submit, submit_async

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
