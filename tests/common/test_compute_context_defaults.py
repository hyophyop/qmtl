import pytest

from qmtl.common.compute_context import ComputeContext, DowngradeReason


def test_default_context_enters_safe_mode_when_domain_missing() -> None:
    ctx = ComputeContext()

    assert ctx.execution_domain == "backtest"
    assert ctx.safe_mode is True
    assert ctx.downgraded is True
    assert ctx.downgrade_reason is DowngradeReason.DECISION_UNAVAILABLE
    assert ctx.hash_components()[1] == "backtest"


def test_dryrun_without_as_of_downgrades_to_compute_only() -> None:
    ctx = ComputeContext(world_id="w", execution_domain="dryrun", as_of=None)

    assert ctx.execution_domain == "backtest"
    assert ctx.safe_mode is True
    assert ctx.downgraded is True
    assert ctx.downgrade_reason is DowngradeReason.MISSING_AS_OF


def test_live_domain_preserves_execution_state() -> None:
    ctx = ComputeContext(world_id="w", execution_domain="live", as_of=None)

    assert ctx.execution_domain == "live"
    assert ctx.safe_mode is False
    assert ctx.downgraded is False
