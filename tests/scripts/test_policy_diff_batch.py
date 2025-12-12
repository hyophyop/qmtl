from __future__ import annotations

import json
from pathlib import Path

from scripts import policy_diff_batch


def _write_policy(tmp_path: Path, sharpe_min: float) -> Path:
    path = tmp_path / f"policy_{sharpe_min}.yml"
    path.write_text(
        f"""
validation_profiles:
  backtest:
    performance:
      sharpe_min: {sharpe_min}
default_profile_by_stage:
  backtest_only: backtest
""".strip(),
        encoding="utf-8",
    )
    return path


def _write_runs(tmp_path: Path) -> Path:
    runs = [
        {"strategy_id": "s1", "metrics": {"sharpe": 1.0}},
        {"strategy_id": "s2", "metrics": {"sharpe": 0.6}},
    ]
    path = tmp_path / "runs.json"
    path.write_text(json.dumps(runs), encoding="utf-8")
    return path


def test_policy_diff_batch_generates_report(tmp_path: Path):
    old_policy = _write_policy(tmp_path, sharpe_min=0.5)
    new_policy = _write_policy(tmp_path, sharpe_min=0.9)
    runs_file = _write_runs(tmp_path)
    output = tmp_path / "report.json"

    report = policy_diff_batch.run_batch(
        old=old_policy,
        new=new_policy,
        runs=[runs_file],
        runs_dir=None,
        runs_pattern="*.json",
        stage="backtest",
        output=output,
        fail_impact_ratio=None,
    )

    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["strategies_affected"] == 1
    assert any(diff["strategy_id"] == "s2" for diff in data["diffs"])
    assert report.impact_ratio > 0


def test_policy_diff_batch_loads_runs_dir(tmp_path: Path):
    old_policy = _write_policy(tmp_path, sharpe_min=0.5)
    new_policy = _write_policy(tmp_path, sharpe_min=0.9)
    runs_file = _write_runs(tmp_path)
    extra_runs = tmp_path / "runs_dir"
    extra_runs.mkdir()
    (extra_runs / "more.json").write_text(json.dumps([{"strategy_id": "s3", "metrics": {"sharpe": 0.6}}]), encoding="utf-8")
    output = tmp_path / "report.json"

    report = policy_diff_batch.run_batch(
        old=old_policy,
        new=new_policy,
        runs=[runs_file],
        runs_dir=extra_runs,
        runs_pattern="*.json",
        stage="backtest",
        output=output,
        fail_impact_ratio=None,
    )

    assert report.total_strategies == 3
    assert any(d.strategy_id == "s3" for d in report.diffs)
