from __future__ import annotations

import math

import pytest

from qmtl.runtime.helpers import (
    apply_temporal_requirements,
    compute_alpha_performance_summary,
    determine_execution_mode,
    normalize_clock_value,
    parse_activation_update,
)
from qmtl.runtime.sdk.execution_context import resolve_execution_context
from qmtl.foundation.common.compute_context import DowngradeReason


def test_determine_execution_mode_prefers_explicit() -> None:
    merged: dict[str, str] = {}

    mode = determine_execution_mode(
        explicit_mode="live",
        execution_domain=None,
        merged_context=merged,
        trade_mode="backtest",
        offline_requested=False,
        gateway_url=None,
    )

    assert mode == "live"


def test_determine_execution_mode_prefers_context_execution_mode() -> None:
    merged = {"execution_mode": "shadow"}

    mode = determine_execution_mode(
        explicit_mode=None,
        execution_domain=None,
        merged_context=merged,
        trade_mode="backtest",
        offline_requested=False,
        gateway_url=None,
    )

    assert mode == "shadow"


def test_determine_execution_mode_accepts_paper_alias() -> None:
    merged: dict[str, str] = {}

    mode = determine_execution_mode(
        explicit_mode="paper",
        execution_domain=None,
        merged_context=merged,
        trade_mode="backtest",
        offline_requested=False,
        gateway_url=None,
    )

    assert mode == "dryrun"


def test_determine_execution_mode_defaults_to_backtest_when_ambiguous() -> None:
    mode = determine_execution_mode(
        explicit_mode=None,
        execution_domain=None,
        merged_context={},
        trade_mode="backtest",
        offline_requested=False,
        gateway_url="https://gateway",
    )

    assert mode == "backtest"


def test_determine_execution_mode_uses_execution_domain_hint() -> None:
    mode = determine_execution_mode(
        explicit_mode=None,
        execution_domain="paper",
        merged_context={},
        trade_mode="backtest",
        offline_requested=False,
        gateway_url="https://gateway",
    )

    assert mode == "dryrun"


def test_resolve_execution_context_downgrades_missing_as_of() -> None:
    resolution = resolve_execution_context(
        None,
        context=None,
        execution_mode="backtest",
        execution_domain=None,
        clock=None,
        as_of=None,
        dataset_fingerprint=None,
        offline_requested=False,
        gateway_url="https://gateway",
        trade_mode="backtest",
    )

    assert resolution.force_offline is True
    assert resolution.downgraded is True
    assert resolution.safe_mode is True
    assert resolution.downgrade_reason == DowngradeReason.MISSING_AS_OF.value
    assert resolution.context["execution_domain"] == "backtest"
    assert resolution.context.get("downgrade_reason") == DowngradeReason.MISSING_AS_OF.value
    assert resolution.context.get("safe_mode") == "true"


def test_resolve_execution_context_accepts_execution_domain_hint() -> None:
    resolution = resolve_execution_context(
        None,
        context=None,
        execution_mode=None,
        execution_domain="paper",
        clock=None,
        as_of="2024-01-01",
        dataset_fingerprint="fingerprint",
        offline_requested=False,
        gateway_url="https://gateway",
        trade_mode="backtest",
    )

    assert resolution.force_offline is False
    assert resolution.context["execution_mode"] == "dryrun"
    assert resolution.context["execution_domain"] == "dryrun"
    assert resolution.downgraded is False
    assert resolution.safe_mode is False


def test_resolve_execution_context_live_not_downgraded_without_as_of() -> None:
    resolution = resolve_execution_context(
        None,
        context=None,
        execution_mode="live",
        execution_domain=None,
        clock=None,
        as_of=None,
        dataset_fingerprint=None,
        offline_requested=False,
        gateway_url="https://gateway",
        trade_mode="live",
    )

    assert resolution.force_offline is False
    assert resolution.downgraded is False
    assert resolution.safe_mode is False
    assert resolution.downgrade_reason is None


@pytest.mark.parametrize("bad_mode", ["offline", "sandbox", "compute-only", "unknown"])
def test_determine_execution_mode_rejects_deprecated_or_unknown_modes(bad_mode: str) -> None:
    merged: dict[str, str] = {}

    with pytest.raises(ValueError):
        determine_execution_mode(
            explicit_mode=bad_mode,
            execution_domain=None,
            merged_context=merged,
            trade_mode="backtest",
            offline_requested=False,
            gateway_url=None,
        )


def test_normalize_clock_value_applies_expected_clock() -> None:
    merged: dict[str, str] = {}

    normalize_clock_value(merged, clock=None, mode="live")

    assert merged["clock"] == "wall"

    with pytest.raises(ValueError):
        normalize_clock_value({}, clock="invalid", mode="live")


def test_normalize_clock_value_prefers_wall_for_shadow() -> None:
    merged: dict[str, str] = {}

    normalize_clock_value(merged, clock=None, mode="shadow")

    assert merged["clock"] == "wall"


def test_apply_temporal_requirements_force_offline() -> None:
    merged: dict[str, str] = {}

    force_offline = apply_temporal_requirements(
        merged,
        mode="backtest",
        as_of=None,
        dataset_fingerprint=None,
        gateway_url="https://gateway",
        offline_requested=False,
    )

    assert force_offline is True
    assert "as_of" not in merged
    assert "dataset_fingerprint" not in merged


def test_apply_temporal_requirements_keeps_complete_fields() -> None:
    merged: dict[str, str] = {}

    force_offline = apply_temporal_requirements(
        merged,
        mode="backtest",
        as_of=" 123 ",
        dataset_fingerprint="abc",
        gateway_url=None,
        offline_requested=False,
    )

    assert force_offline is False
    assert merged["as_of"] == "123"
    assert merged["dataset_fingerprint"] == "abc"


def test_apply_temporal_requirements_treats_shadow_as_live() -> None:
    merged: dict[str, str] = {}

    force_offline = apply_temporal_requirements(
        merged,
        mode="shadow",
        as_of="2024-01-01",
        dataset_fingerprint="dfp",
        gateway_url="https://gateway",
        offline_requested=False,
    )

    assert force_offline is False
    assert "as_of" not in merged
    assert "dataset_fingerprint" not in merged


def test_parse_activation_update_clamps_weight() -> None:
    update = parse_activation_update(
        {
            "side": "LONG",
            "active": 1,
            "freeze": 0,
            "drain": 1,
            "weight": 1.5,
            "version": "4",
            "etag": " etag ",
            "run_id": " run ",
            "ts": " 2024-01-01T00:00:00Z ",
            "state_hash": " hash ",
            "effective_mode": " Live ",
        }
    )

    assert update.side == "long"
    assert update.active is True
    assert update.freeze is False
    assert update.drain is True
    assert update.weight == pytest.approx(1.0)
    assert update.metadata.version == 4
    assert update.metadata.etag == "etag"
    assert update.metadata.run_id == "run"
    assert update.metadata.ts == "2024-01-01T00:00:00Z"
    assert update.metadata.state_hash == "hash"
    assert update.metadata.effective_mode == "Live"


def test_parse_activation_update_ignores_invalid_weight() -> None:
    update = parse_activation_update(
        {
            "side": "short",
            "active": 0,
            "weight": "oops",
        }
    )

    assert update.weight is None
    assert update.active is False


def test_compute_alpha_performance_summary_handles_empty_returns() -> None:
    result = compute_alpha_performance_summary([])

    assert result == {
        "alpha_performance.sharpe": 0.0,
        "alpha_performance.max_drawdown": 0.0,
        "alpha_performance.win_ratio": 0.0,
        "alpha_performance.profit_factor": 0.0,
        "alpha_performance.car_mdd": 0.0,
        "alpha_performance.rar_mdd": 0.0,
    }


def test_compute_alpha_performance_summary_includes_execution_metrics() -> None:
    returns = [0.02, -0.01, 0.015]
    fills = [
        type("Fill", (), {
            "commission": 1.0,
            "slippage": 0.0005,
            "quantity": 100,
            "market_impact": 0.0002,
            "execution_shortfall": 0.0003,
        })()
    ]

    result = compute_alpha_performance_summary(
        returns,
        execution_fills=fills,
        use_realistic_costs=True,
    )

    assert "alpha_performance.sharpe" in result
    assert math.isfinite(result["alpha_performance.sharpe"])
    assert result["execution_total_trades"] == 1
