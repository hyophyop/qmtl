#!/usr/bin/env python3
"""Batch runner for policy diffs (supports CI/cron).

This wrapper orchestrates multiple policy diff runs (e.g., "bad strategy" set + latest runs)
and emits a JSON summary that can be used as a CI artifact or alert trigger.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from scripts.policy_diff import (
    PolicyDiffReport,
    StrategyDiff,
    _compare_rule_results,
    _extract_metrics,
    _get_summary_status,
    _load_policy,
    _load_runs,
    evaluate_policy,
)
from qmtl.services.worldservice.policy_engine import Policy


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


def run_diff(
    old_policy: Policy,
    new_policy: Policy,
    runs: list[dict[str, Any]],
    *,
    stage: str = "backtest",
) -> PolicyDiffReport:
    strategies = sorted({str(run.get("strategy_id")) for run in runs if run.get("strategy_id")})
    metrics = {sid: _extract_metrics(run) for sid, run in ((str(r.get("strategy_id")), r) for r in runs) if sid}
    result_old = evaluate_policy(metrics=metrics, policy=old_policy, stage=stage)
    result_new = evaluate_policy(metrics=metrics, policy=new_policy, stage=stage)

    diffs: list[StrategyDiff] = []
    selection_changes = stage_changes = status_changes = 0
    for sid in strategies:
        old_selected = sid in result_old.selected_ids
        new_selected = sid in result_new.selected_ids
        old_stage = result_old.recommended_stage if isinstance(result_old.recommended_stage, str) else None
        new_stage = result_new.recommended_stage if isinstance(result_new.recommended_stage, str) else None
        old_status = _get_summary_status(result_old, sid)
        new_status = _get_summary_status(result_new, sid)
        rule_changes = _compare_rule_results(result_old, result_new, sid)
        if old_selected != new_selected:
            selection_changes += 1
        if old_stage != new_stage:
            stage_changes += 1
        if old_status != new_status:
            status_changes += 1
        diffs.append(
            StrategyDiff(
                strategy_id=sid,
                old_selected=old_selected,
                new_selected=new_selected,
                old_recommended_stage=old_stage,
                new_recommended_stage=new_stage,
                old_status=old_status,
                new_status=new_status,
                rule_changes=rule_changes,
            )
        )

    report = PolicyDiffReport(
        old_policy_version=str(getattr(old_policy, "version", None) or old_policy.model_dump().get("version")),
        new_policy_version=str(getattr(new_policy, "version", None) or new_policy.model_dump().get("version")),
        old_ruleset_hash=None,
        new_ruleset_hash=None,
        total_strategies=len(strategies),
        strategies_affected=sum(1 for d in diffs if d.has_changes),
        selection_changes=selection_changes,
        stage_changes=stage_changes,
        status_changes=status_changes,
        diffs=[],  # filled below
    )
    # keep only changed entries in the output for brevity
    report.diffs = [d for d in diffs if d.has_changes]
    return report


def run_batch(
    *,
    old: Path,
    new: Path,
    runs: list[Path],
    runs_dir: Path | None,
    runs_pattern: str,
    stage: str,
    output: Path,
    fail_impact_ratio: float | None,
) -> PolicyDiffReport:
    old_policy = _load_policy(old)
    new_policy = _load_policy(new)
    merged_runs = _collect_runs(runs, runs_dir, runs_pattern)
    report = run_diff(old_policy, new_policy, merged_runs, stage=stage)
    output.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

    if fail_impact_ratio is not None and report.impact_ratio >= fail_impact_ratio:
        raise SystemExit(f"Impact ratio {report.impact_ratio:.2f} exceeds threshold {fail_impact_ratio}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch policy diff runner (CI/cron friendly)")
    parser.add_argument("--old", required=True, type=Path, help="Path to old policy YAML/JSON")
    parser.add_argument("--new", required=True, type=Path, help="Path to new policy YAML/JSON")
    parser.add_argument("--runs", nargs="+", type=Path, default=[], help="One or more runs files (JSON/YAML)")
    parser.add_argument("--runs-dir", type=Path, default=None, help="Directory containing runs files")
    parser.add_argument("--runs-pattern", default="*.json", help="Glob pattern for runs-dir (default: *.json)")
    parser.add_argument("--stage", default="backtest", help="Validation stage (backtest/paper/live)")
    parser.add_argument("--output", type=Path, default=Path("policy_diff_report.json"), help="Output JSON path")
    parser.add_argument("--fail-impact-ratio", type=float, default=None, help="Fail if impacted ratio >= threshold (0~1)")
    args = parser.parse_args()

    run_batch(
        old=args.old,
        new=args.new,
        runs=args.runs,
        runs_dir=args.runs_dir,
        runs_pattern=args.runs_pattern,
        stage=args.stage,
        output=args.output,
        fail_impact_ratio=args.fail_impact_ratio,
    )


if __name__ == "__main__":
    main()
