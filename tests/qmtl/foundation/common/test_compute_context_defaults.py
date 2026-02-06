import pytest

from qmtl.foundation.common.compute_context import (
    ComputeContext,
    DowngradeReason,
    build_worldservice_compute_context,
)


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


def test_worldservice_mode_sim_alias_maps_to_dryrun() -> None:
    ctx = build_worldservice_compute_context(
        "w",
        {
            "effective_mode": "sim",
            "as_of": "2025-01-01T00:00:00Z",
        },
    )

    assert ctx.execution_domain == "dryrun"
    assert ctx.safe_mode is False
    assert ctx.downgraded is False
