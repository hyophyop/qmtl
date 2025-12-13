from __future__ import annotations

from scripts import policy_snapshot_diff


def test_policy_snapshot_diff_detects_changes():
    old = {
        "revision": "base",
        "policy_version": "p1",
        "ruleset_hash": "blake3:old",
        "recommended_stage": "backtest_only",
        "strategies": {
            "s1": {"selected": True, "status": "pass", "rule_results": {"r1": {"status": "pass"}}},
            "s2": {"selected": False, "status": "fail", "rule_results": {"r1": {"status": "fail"}}},
        },
    }
    new = {
        "revision": "head",
        "policy_version": "p2",
        "ruleset_hash": "blake3:new",
        "recommended_stage": "paper_only",
        "strategies": {
            "s1": {"selected": True, "status": "warn", "rule_results": {"r1": {"status": "warn"}}},
            "s2": {"selected": True, "status": "fail", "rule_results": {"r1": {"status": "fail"}}},
        },
    }

    report = policy_snapshot_diff.diff_snapshots(old, new)
    assert report.total_strategies == 2
    assert report.strategies_affected == 2
    assert report.selection_changes == 1  # s2
    assert report.status_changes == 1     # s1
    assert report.stage_changes == 2      # recommended_stage changed
    assert report.impact_ratio == 1.0
