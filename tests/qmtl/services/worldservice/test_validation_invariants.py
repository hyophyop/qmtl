from __future__ import annotations

from datetime import datetime, timedelta, timezone

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


# =============================================================================
# Phase 1: Enhanced Invariant Tests (§12 of world_validation_architecture.md)
# =============================================================================


class TestInvariant1LiveStatusConsistency:
    """Invariant 1 — live 단계 정합성 (§12.1)

    stage=live 또는 effective_mode=live인 전략은:
    - 최신 EvaluationRun의 summary.status가 반드시 "pass"여야 한다.
    - 최신 EvaluationRun의 validation.policy_version이 WorldPolicy 버전과 호환되어야 한다.
    """

    def test_live_strategy_with_pass_status_is_ok(self):
        world = {"id": "world-prod"}
        runs = [
            {
                "world_id": "world-prod",
                "strategy_id": "strat-live",
                "run_id": "run-1",
                "stage": "live",
                "summary": {"status": "pass"},
                "metrics": ensure_validation_health(_full_metrics(), {"performance": {"status": "pass"}}),
                "validation": {"results": {"performance": {"status": "pass"}}},
                "created_at": "2025-01-01T00:00:00+00:00",
            }
        ]

        report = check_validation_invariants(world, runs)

        assert report.ok
        assert len(report.live_status_failures) == 0

    def test_live_strategy_with_fail_status_is_flagged(self):
        world = {"id": "world-prod"}
        runs = [
            {
                "world_id": "world-prod",
                "strategy_id": "strat-failing",
                "run_id": "run-fail",
                "stage": "live",
                "summary": {"status": "fail"},
                "metrics": _full_metrics(),
                "validation": {"results": {"performance": {"status": "fail"}}},
                "created_at": "2025-01-01T00:00:00+00:00",
            }
        ]

        report = check_validation_invariants(world, runs)

        assert not report.ok
        assert len(report.live_status_failures) == 1
        failure = report.live_status_failures[0]
        assert failure["strategy_id"] == "strat-failing"
        assert failure["status"] == "fail"

    def test_live_strategy_with_warn_status_is_flagged(self):
        world = {"id": "world-prod"}
        runs = [
            {
                "world_id": "world-prod",
                "strategy_id": "strat-warning",
                "run_id": "run-warn",
                "stage": "live",
                "summary": {"status": "warn"},
                "metrics": _full_metrics(),
                "validation": {"results": {}},
                "created_at": "2025-01-01T00:00:00+00:00",
            }
        ]

        report = check_validation_invariants(world, runs)

        assert not report.ok
        assert len(report.live_status_failures) == 1

    def test_live_strategy_with_outdated_policy_version_is_flagged(self):
        world = {"id": "world-prod", "default_policy_version": 3}
        runs = [
            {
                "world_id": "world-prod",
                "strategy_id": "strat-outdated",
                "run_id": "run-legacy",
                "stage": "live",
                "summary": {"status": "pass"},
                "metrics": ensure_validation_health(
                    _full_metrics(), {"performance": {"status": "pass"}}
                ),
                "validation": {"results": {"performance": {"status": "pass"}}, "policy_version": "2"},
                "created_at": "2025-01-01T00:00:00+00:00",
            }
        ]

        report = check_validation_invariants(world, runs)

        assert not report.ok
        assert len(report.live_policy_version_mismatches) == 1
        mismatch = report.live_policy_version_mismatches[0]
        assert mismatch["policy_version"] == "2"
        assert mismatch["required_policy_version"] == 3

    def test_live_strategy_without_policy_version_is_flagged(self):
        world = {"id": "world-prod", "default_policy_version": 1}
        runs = [
            {
                "world_id": "world-prod",
                "strategy_id": "strat-missing",
                "run_id": "run-missing",
                "stage": "live",
                "summary": {"status": "pass"},
                "metrics": ensure_validation_health(
                    _full_metrics(), {"performance": {"status": "pass"}}
                ),
                "validation": {"results": {"performance": {"status": "pass"}}},
                "created_at": "2025-01-01T00:00:00+00:00",
            }
        ]

        report = check_validation_invariants(world, runs)

        assert not report.ok
        assert len(report.live_policy_version_mismatches) == 1

    def test_live_policy_version_meeting_world_requirement_is_ok(self):
        world = {"id": "world-prod", "default_policy_version": 2}
        runs = [
            {
                "world_id": "world-prod",
                "strategy_id": "strat-current",
                "run_id": "run-current",
                "stage": "live",
                "summary": {"status": "pass"},
                "metrics": ensure_validation_health(
                    _full_metrics(), {"performance": {"status": "pass"}}
                ),
                "validation": {
                    "results": {"performance": {"status": "pass"}},
                    "policy_version": "2",
                },
                "created_at": "2025-01-02T00:00:00+00:00",
            }
        ]

        report = check_validation_invariants(world, runs)

        assert report.ok
        assert len(report.live_policy_version_mismatches) == 0

    def test_multiple_live_strategies_only_latest_per_strategy_checked(self):
        """각 전략별 최신 run만 검사한다."""
        world = {"id": "world-prod"}
        runs = [
            {
                "world_id": "world-prod",
                "strategy_id": "strat-a",
                "run_id": "old-fail",
                "stage": "live",
                "summary": {"status": "fail"},  # 이전 실패
                "metrics": _full_metrics(),
                "validation": {"results": {}},
                "created_at": "2025-01-01T00:00:00+00:00",
            },
            {
                "world_id": "world-prod",
                "strategy_id": "strat-a",
                "run_id": "new-pass",
                "stage": "live",
                "summary": {"status": "pass"},  # 최신 성공
                "metrics": ensure_validation_health(_full_metrics(), {"performance": {"status": "pass"}}),
                "validation": {"results": {"performance": {"status": "pass"}}},
                "created_at": "2025-02-01T00:00:00+00:00",
            },
        ]

        report = check_validation_invariants(world, runs)

        # 최신 run이 pass이므로 ok
        assert len(report.live_status_failures) == 0

    def test_backtest_and_paper_stages_not_flagged_for_live_invariant(self):
        """live가 아닌 stage는 Invariant 1 대상이 아니다."""
        world = {"id": "world-dev"}
        runs = [
            {
                "world_id": "world-dev",
                "strategy_id": "strat-dev",
                "run_id": "run-backtest-fail",
                "stage": "backtest",
                "summary": {"status": "fail"},
                "metrics": _full_metrics(),
                "validation": {"results": {}},
                "created_at": "2025-01-01T00:00:00+00:00",
            },
            {
                "world_id": "world-dev",
                "strategy_id": "strat-dev",
                "run_id": "run-paper-warn",
                "stage": "paper",
                "summary": {"status": "warn"},
                "metrics": _full_metrics(),
                "validation": {"results": {}},
                "created_at": "2025-01-02T00:00:00+00:00",
            },
        ]

        report = check_validation_invariants(world, runs)

        # live 전략이 없으므로 live_status_failures는 비어있어야 함
        assert len(report.live_status_failures) == 0


class TestInvariant2FailClosedPolicy:
    """Invariant 2 — high‑tier World의 fail‑closed 정책 (§12.2)

    risk_profile.tier=high 및 client_critical=true인 World에서는:
    - validation.on_error와 validation.on_missing_metric은 항상 "fail"이어야 한다.
    """

    def test_high_tier_critical_world_with_fail_closed_is_ok(self):
        world = {
            "id": "world-high-critical",
            "risk_profile": {"tier": "high", "client_critical": True},
            "validation": {"on_error": "fail", "on_missing_metric": "fail"},
        }

        report = check_validation_invariants(world, [])

        assert len(report.fail_closed_violations) == 0

    def test_high_tier_critical_world_with_warn_on_error_is_violation(self):
        world = {
            "id": "world-high-critical",
            "risk_profile": {"tier": "high", "client_critical": True},
            "validation": {"on_error": "warn", "on_missing_metric": "fail"},
        }

        report = check_validation_invariants(world, [])

        assert len(report.fail_closed_violations) == 1
        violation = report.fail_closed_violations[0]
        assert violation["on_error"] == "warn"

    def test_high_tier_critical_world_with_ignore_on_missing_is_violation(self):
        world = {
            "id": "world-high-critical",
            "risk_profile": {"tier": "high", "client_critical": True},
            "validation": {"on_error": "fail", "on_missing_metric": "ignore"},
        }

        report = check_validation_invariants(world, [])

        assert len(report.fail_closed_violations) == 1
        violation = report.fail_closed_violations[0]
        assert violation["on_missing_metric"] == "ignore"

    def test_high_tier_non_critical_world_not_enforced(self):
        """client_critical=false이면 fail-closed 강제 대상이 아니다."""
        world = {
            "id": "world-high-internal",
            "risk_profile": {"tier": "high", "client_critical": False},
            "validation": {"on_error": "warn", "on_missing_metric": "warn"},
        }

        report = check_validation_invariants(world, [])

        assert len(report.fail_closed_violations) == 0

    def test_medium_tier_critical_world_not_enforced(self):
        """tier=medium이면 fail-closed 강제 대상이 아니다."""
        world = {
            "id": "world-medium-critical",
            "risk_profile": {"tier": "medium", "client_critical": True},
            "validation": {"on_error": "warn", "on_missing_metric": "warn"},
        }

        report = check_validation_invariants(world, [])

        assert len(report.fail_closed_violations) == 0

    def test_low_tier_world_not_enforced(self):
        """tier=low이면 fail-closed 강제 대상이 아니다."""
        world = {
            "id": "world-low",
            "risk_profile": {"tier": "low"},
            "validation": {"on_error": "warn"},
        }

        report = check_validation_invariants(world, [])

        assert len(report.fail_closed_violations) == 0

    def test_missing_validation_block_in_high_tier_critical_is_violation(self):
        """validation 블록 없이 on_error/on_missing_metric이 없으면 violation."""
        world = {
            "id": "world-high-no-validation",
            "risk_profile": {"tier": "high", "client_critical": True},
        }

        report = check_validation_invariants(world, [])

        assert len(report.fail_closed_violations) == 1


class TestInvariant3OverrideManagement:
    """Invariant 3 — override 관리 (§12.3)

    override_status=approved인 EvaluationRun은:
    - 별도 목록으로 집계되어야 하며,
    - override_reason, override_actor, override_timestamp는 필수 기록 필드다.
    """

    def test_approved_override_is_collected(self):
        world = {"id": "world-override"}
        runs = [
            {
                "world_id": "world-override",
                "strategy_id": "strat-override",
                "run_id": "run-override",
                "stage": "paper",
                "summary": {
                    "status": "warn",
                    "override_status": "approved",
                    "override_reason": "Risk committee approved exception",
                    "override_actor": "risk-manager@example.com",
                    "override_timestamp": "2025-01-15T10:00:00Z",
                },
                "metrics": _full_metrics(),
                "validation": {"results": {}},
                "created_at": "2025-01-10T00:00:00+00:00",
            }
        ]

        report = check_validation_invariants(world, runs)

        assert len(report.approved_overrides) == 1
        override = report.approved_overrides[0]
        assert override["run_id"] == "run-override"
        assert override["override_reason"] == "Risk committee approved exception"

    def test_rejected_override_not_collected(self):
        world = {"id": "world-override"}
        runs = [
            {
                "world_id": "world-override",
                "strategy_id": "strat-rejected",
                "run_id": "run-rejected",
                "stage": "paper",
                "summary": {
                    "status": "fail",
                    "override_status": "rejected",
                    "override_reason": "Insufficient justification",
                },
                "metrics": _full_metrics(),
                "validation": {"results": {}},
                "created_at": "2025-01-10T00:00:00+00:00",
            }
        ]

        report = check_validation_invariants(world, runs)

        assert len(report.approved_overrides) == 0

    def test_no_override_status_not_collected(self):
        world = {"id": "world-normal"}
        runs = [
            {
                "world_id": "world-normal",
                "strategy_id": "strat-normal",
                "run_id": "run-normal",
                "stage": "backtest",
                "summary": {"status": "pass"},
                "metrics": ensure_validation_health(_full_metrics(), {"performance": {"status": "pass"}}),
                "validation": {"results": {"performance": {"status": "pass"}}},
                "created_at": "2025-01-10T00:00:00+00:00",
            }
        ]

        report = check_validation_invariants(world, runs)

        assert len(report.approved_overrides) == 0

    def test_multiple_approved_overrides_all_collected(self):
        world = {"id": "world-multi-override"}
        runs = [
            {
                "world_id": "world-multi-override",
                "strategy_id": "strat-a",
                "run_id": "run-a",
                "stage": "paper",
                "summary": {"status": "warn", "override_status": "approved"},
                "metrics": _full_metrics(),
                "validation": {"results": {}},
                "created_at": "2025-01-10T00:00:00+00:00",
            },
            {
                "world_id": "world-multi-override",
                "strategy_id": "strat-b",
                "run_id": "run-b",
                "stage": "live",
                "summary": {"status": "warn", "override_status": "approved"},
                "metrics": _full_metrics(),
                "validation": {"results": {}},
                "created_at": "2025-01-12T00:00:00+00:00",
            },
        ]

        report = check_validation_invariants(world, runs)

        assert len(report.approved_overrides) == 2
        run_ids = {o["run_id"] for o in report.approved_overrides}
        assert run_ids == {"run-a", "run-b"}


class TestValidationHealthGaps:
    """validation_health 지표 불일치 감지 테스트."""

    def test_metrics_without_validation_health_flagged(self):
        world = {"id": "world-health"}
        runs = [
            {
                "world_id": "world-health",
                "strategy_id": "strat-no-health",
                "run_id": "run-no-health",
                "stage": "backtest",
                "summary": {"status": "pass"},
                "metrics": _full_metrics(),  # validation_health 없음
                "validation": {"results": {"performance": {"status": "pass"}}},
                "created_at": "2025-01-10T00:00:00+00:00",
            }
        ]

        report = check_validation_invariants(world, runs)

        # validation_health가 없으면 gap으로 처리됨
        assert len(report.validation_health_gaps) > 0

    def test_metrics_with_correct_validation_health_not_flagged(self):
        world = {"id": "world-health"}
        rule_results = {"performance": {"status": "pass"}, "sample": {"status": "pass"}}
        runs = [
            {
                "world_id": "world-health",
                "strategy_id": "strat-healthy",
                "run_id": "run-healthy",
                "stage": "backtest",
                "summary": {"status": "pass"},
                "metrics": ensure_validation_health(_full_metrics(), rule_results),
                "validation": {"results": rule_results},
                "created_at": "2025-01-10T00:00:00+00:00",
            }
        ]

        report = check_validation_invariants(world, runs)

        # ensure_validation_health로 올바르게 계산된 경우
        health_gaps_for_run = [g for g in report.validation_health_gaps if g["run_id"] == "run-healthy"]
        assert len(health_gaps_for_run) == 0


def test_invariant3_override_rereview_due_date_and_overdue_flag():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    override_ts = now - timedelta(days=40)
    override_raw = override_ts.isoformat().replace("+00:00", "Z")
    world = {"id": "world-prod"}
    run = {
        "world_id": "world-prod",
        "strategy_id": "strat-override",
        "run_id": "override-live",
        "stage": "live",
        "summary": {
            "status": "warn",
            "override_status": "approved",
            "override_reason": "temporary risk waiver",
            "override_actor": "risk",
            "override_timestamp": override_raw,
        },
        "validation": {"results": {"performance": {"status": "warn"}}},
        "metrics": ensure_validation_health(_full_metrics(), {"performance": {"status": "warn"}}),
        "created_at": override_raw,
    }

    report = check_validation_invariants(world, [run])

    assert not report.ok
    assert len(report.approved_overrides) == 1
    entry = report.approved_overrides[0]
    assert entry["review_window_days"] == 30
    expected_due = (override_ts + timedelta(days=30)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    assert entry["review_due_at"] == expected_due
    assert entry["review_overdue"] is True
    assert entry["missing_fields"] == []


class TestInvariantReportOkProperty:
    """InvariantReport.ok 속성 동작 검증."""

    def test_empty_report_is_ok(self):
        world = {"id": "world-clean"}
        runs = []

        report = check_validation_invariants(world, runs)

        assert report.ok

    def test_any_failure_makes_report_not_ok(self):
        world = {"id": "world-failure"}
        runs = [
            {
                "world_id": "world-failure",
                "strategy_id": "strat-live-fail",
                "run_id": "run-live-fail",
                "stage": "live",
                "summary": {"status": "fail"},
                "metrics": _full_metrics(),
                "validation": {"results": {}},
                "created_at": "2025-01-10T00:00:00+00:00",
            }
        ]

        report = check_validation_invariants(world, runs)

        assert not report.ok
