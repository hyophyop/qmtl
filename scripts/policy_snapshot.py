#!/usr/bin/env python3
"""Policy evaluation snapshot tool.

This script evaluates a single policy against a set of EvaluationRun-like payloads
and emits a stable JSON snapshot. It is intended to support CI regression gates
for validation rules/policy changes (base vs head comparisons).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from scripts.policy_diff import _extract_metrics, _load_policy, _load_runs, _get_summary_status
from qmtl.services.worldservice.policy_engine import Policy, RuleResult, evaluate_policy


def _merge_runs(paths: Iterable[Path]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for path in paths:
        merged.extend(_load_runs(path))
    return merged


def _collect_runs(runs: list[Path], runs_dir: Path | None, runs_pattern: str) -> list[dict[str, Any]]:
    paths: list[Path] = list(runs)
    if runs_dir:
        paths.extend(sorted(runs_dir.glob(runs_pattern)))
    return _merge_runs(paths)


def _rule_to_dict(rule: RuleResult) -> dict[str, Any]:
    return {
        "status": rule.status,
        "severity": rule.severity,
        "owner": rule.owner,
        "reason_code": rule.reason_code,
        "reason": rule.reason,
        "tags": list(rule.tags),
        "details": dict(rule.details),
    }


def snapshot_policy(
    policy: Policy,
    runs: Sequence[Mapping[str, Any]],
    *,
    stage: str = "backtest",
    policy_version: str | None = None,
    revision: str | None = None,
) -> dict[str, Any]:
    metrics_map: dict[str, dict[str, Any]] = {}
    for run in runs:
        strategy_id = run.get("strategy_id")
        if not strategy_id:
            continue
        metrics_map[str(strategy_id)] = _extract_metrics(run)

    result = evaluate_policy(metrics_map, policy, stage=stage, policy_version=policy_version)
    selected = set(result.selected_ids)

    strategies: dict[str, Any] = {}
    for strategy_id in sorted(metrics_map.keys()):
        rules = result.rule_results.get(strategy_id, {})
        strategies[strategy_id] = {
            "selected": strategy_id in selected,
            "status": _get_summary_status(result, strategy_id),
            "rule_results": {name: _rule_to_dict(rule) for name, rule in sorted(rules.items())},
        }

    return {
        "revision": revision,
        "policy_version": str(policy_version or result.policy_version or getattr(policy, "version", None) or ""),
        "ruleset_hash": result.ruleset_hash,
        "profile": result.profile,
        "recommended_stage": result.recommended_stage,
        "stage": stage,
        "total_strategies": len(metrics_map),
        "strategies": strategies,
    }


def run_snapshot(
    *,
    policy_path: Path,
    runs: list[Path],
    runs_dir: Path | None,
    runs_pattern: str,
    stage: str,
    output: Path,
    policy_version: str | None,
    revision: str | None,
) -> dict[str, Any]:
    policy = _load_policy(policy_path)
    merged_runs = _collect_runs(runs, runs_dir, runs_pattern)
    snapshot = snapshot_policy(policy, merged_runs, stage=stage, policy_version=policy_version, revision=revision)
    output.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Emit a stable policy evaluation snapshot (JSON).")
    parser.add_argument("--policy", required=True, type=Path, help="Path to policy YAML/JSON")
    parser.add_argument("--runs", nargs="+", type=Path, default=[], help="One or more runs files (JSON/YAML)")
    parser.add_argument("--runs-dir", type=Path, default=None, help="Directory containing runs files")
    parser.add_argument("--runs-pattern", default="*.json", help="Glob pattern for runs-dir (default: *.json)")
    parser.add_argument("--stage", default="backtest", help="Validation stage (backtest/paper/live)")
    parser.add_argument("--output", type=Path, default=Path("policy_snapshot.json"), help="Output JSON path")
    parser.add_argument("--policy-version", default=None, help="Override policy_version recorded in snapshot")
    parser.add_argument("--revision", default=None, help="Optional revision label (e.g., git SHA)")
    args = parser.parse_args()

    run_snapshot(
        policy_path=args.policy,
        runs=list(args.runs),
        runs_dir=args.runs_dir,
        runs_pattern=str(args.runs_pattern),
        stage=str(args.stage),
        output=args.output,
        policy_version=args.policy_version,
        revision=args.revision,
    )


if __name__ == "__main__":
    main()
