from __future__ import annotations

from scripts import policy_scenario_check


def test_policy_scenario_check_summarizes_statuses():
    snapshot = {
        "strategies": {
            "s1": {"status": "pass"},
            "s2": {"status": "warn"},
            "s3": {"status": "fail"},
            "s4": {"status": "weird"},
        }
    }

    summary = policy_scenario_check.summarize_snapshot(snapshot)
    assert summary.total == 4
    assert summary.passed == 1
    assert summary.warned == 1
    assert summary.failed == 1
    assert summary.unknown == 1


def test_policy_scenario_check_enforces_ratio_thresholds():
    snapshot = {
        "strategies": {
            "s1": {"status": "pass"},
            "s2": {"status": "pass"},
            "s3": {"status": "fail"},
            "s4": {"status": "fail"},
        }
    }

    summary, errors = policy_scenario_check.check_snapshot(
        snapshot,
        min_pass_ratio=0.75,
        max_pass_ratio=None,
        min_warn_ratio=None,
        max_warn_ratio=None,
        min_fail_ratio=None,
        max_fail_ratio=0.1,
        min_unknown_ratio=None,
        max_unknown_ratio=0.0,
    )

    assert summary.total == 4
    assert errors
    assert any("pass_ratio" in message for message in errors)
    assert any("fail_ratio" in message for message in errors)
