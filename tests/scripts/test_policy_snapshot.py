from __future__ import annotations

import json
from pathlib import Path

from scripts import policy_snapshot


def _write_policy(tmp_path: Path, sharpe_min: float) -> Path:
    path = tmp_path / "policy.yml"
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
        {"strategy_id": "s2", "metrics": {"sharpe": 0.2}},
    ]
    path = tmp_path / "runs.json"
    path.write_text(json.dumps(runs), encoding="utf-8")
    return path


def test_policy_snapshot_emits_stable_schema(tmp_path: Path):
    policy_path = _write_policy(tmp_path, sharpe_min=0.5)
    runs_path = _write_runs(tmp_path)
    output = tmp_path / "snapshot.json"

    snapshot = policy_snapshot.run_snapshot(
        policy_path=policy_path,
        runs=[runs_path],
        runs_dir=None,
        runs_pattern="*.json",
        stage="backtest",
        output=output,
        policy_version="test-policy",
        revision="revA",
    )

    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["revision"] == "revA"
    assert data["policy_version"] == "test-policy"
    assert data["ruleset_hash"] and data["ruleset_hash"].startswith("blake3:")
    assert data["total_strategies"] == 2
    assert set(data["strategies"].keys()) == {"s1", "s2"}
    assert snapshot["strategies"]["s1"]["status"] in {"pass", "warn", "fail", None}
