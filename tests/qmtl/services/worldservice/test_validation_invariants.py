from __future__ import annotations

import pytest

from qmtl.services.worldservice.validation_checks import (
    DEFAULT_RULE_COUNT,
    check_validation_invariants,
    ensure_validation_health,
)


def _full_metrics() -> dict:
    return {
        "returns": {
            "sharpe": 1.2,
            "max_drawdown": -0.1,
            "gain_to_pain_ratio": 1.5,
            "time_under_water_ratio": 0.2,
        },
        "sample": {
            "effective_history_years": 3.5,
            "n_trades_total": 210,
            "n_trades_per_year": 70.0,
        },
        "risk": {
            "adv_utilization_p95": 0.2,
            "participation_rate_p95": 0.15,
        },
        "robustness": {
            "deflated_sharpe_ratio": 0.3,
            "sharpe_first_half": 0.4,
            "sharpe_second_half": 0.5,
        },
    }


def test_ensure_validation_health_computes_ratios_without_mutation():
    metrics = _full_metrics()
    rule_results = {
        "sample": {"status": "pass"},
        "performance": {"status": "pass"},
        "risk": {"status": "warn"},
    }

    enriched = ensure_validation_health(metrics, rule_results)

    assert "diagnostics" not in metrics  # original untouched
    health = enriched["diagnostics"]["validation_health"]
    assert health["metric_coverage_ratio"] == pytest.approx(1.0)
    assert health["rules_executed_ratio"] == pytest.approx(len(rule_results) / DEFAULT_RULE_COUNT)


def test_check_invariants_flags_latest_live_failure():
    metrics = ensure_validation_health(
        _full_metrics(),
        {"performance": {"status": "pass"}, "risk": {"status": "pass"}},
    )
    runs = [
        {
            "world_id": "world-live",
            "strategy_id": "strat-a",
            "run_id": "live-pass",
            "stage": "live",
            "summary": {"status": "pass"},
            "metrics": metrics,
            "validation": {"results": {"performance": {"status": "pass"}}},
            "created_at": "2025-01-01T00:00:00+00:00",
        },
        {
            "world_id": "world-live",
            "strategy_id": "strat-a",
            "run_id": "live-fail",
            "stage": "live",
            "summary": {"status": "fail"},
            "metrics": metrics,
            "validation": {"results": {"performance": {"status": "fail"}}},
            "created_at": "2025-02-01T00:00:00+00:00",
        },
    ]

    report = check_validation_invariants({"id": "world-live"}, runs)

    assert any(v["run_id"] == "live-fail" for v in report.live_status_failures)


def test_check_invariants_enforces_fail_closed_and_collects_overrides():
    world = {
        "id": "world-risky",
        "risk_profile": {"tier": "high", "client_critical": True},
        "validation": {"on_error": "warn", "on_missing_metric": "fail"},
    }
    override_run = {
        "world_id": "world-risky",
        "strategy_id": "strat-b",
        "run_id": "override-run",
        "stage": "paper",
        "summary": {"status": "warn", "override_status": "approved"},
        "validation": {"results": {}},
        "metrics": {"returns": {"sharpe": 1.0}},
        "created_at": "2025-01-10T00:00:00+00:00",
    }
    healthy_run = {
        "world_id": "world-risky",
        "strategy_id": "strat-c",
        "run_id": "healthy-run",
        "stage": "paper",
        "summary": {"status": "pass"},
        "validation": {"results": {"performance": {"status": "pass"}}},
        "metrics": ensure_validation_health(
            _full_metrics(),
            {"performance": {"status": "pass"}},
        ),
        "created_at": "2025-01-05T00:00:00+00:00",
    }

    report = check_validation_invariants(world, [override_run, healthy_run])

    assert report.fail_closed_violations and report.fail_closed_violations[0]["world_id"] == "world-risky"
    assert any(item["run_id"] == "override-run" for item in report.approved_overrides)
    assert any(gap["run_id"] == "override-run" for gap in report.validation_health_gaps)
    assert not any(gap["run_id"] == "healthy-run" for gap in report.validation_health_gaps)
