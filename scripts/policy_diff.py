#!/usr/bin/env python3
"""Policy diff simulation tool.

This script compares the impact of policy changes on historical EvaluationRuns.
It helps identify unintended consequences before deploying policy updates.

Usage:
    python scripts/policy_diff.py --old policy_v1.yaml --new policy_v2.yaml --runs runs.json
    python scripts/policy_diff.py --old policy_v1.yaml --new policy_v2.yaml --runs runs.json --output diff_report.md

Reference: world_validation_architecture.md §11.3 (Policy Diff)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from qmtl.services.worldservice.policy_engine import (
    Policy,
    PolicyEvaluationResult,
    evaluate_policy,
    parse_policy,
)


@dataclass
class StrategyDiff:
    """Diff result for a single strategy."""

    strategy_id: str
    old_selected: bool
    new_selected: bool
    old_recommended_stage: str | None
    new_recommended_stage: str | None
    old_status: str | None
    new_status: str | None
    rule_changes: list[dict[str, Any]] = field(default_factory=list)

    @property
    def selection_changed(self) -> bool:
        return self.old_selected != self.new_selected

    @property
    def stage_changed(self) -> bool:
        return self.old_recommended_stage != self.new_recommended_stage

    @property
    def status_changed(self) -> bool:
        return self.old_status != self.new_status

    @property
    def has_changes(self) -> bool:
        return self.selection_changed or self.stage_changed or self.status_changed or bool(self.rule_changes)


@dataclass
class PolicyDiffReport:
    """Aggregate diff report across all strategies."""

    old_policy_version: str | None
    new_policy_version: str | None
    old_ruleset_hash: str | None
    new_ruleset_hash: str | None
    total_strategies: int
    strategies_affected: int
    selection_changes: int
    stage_changes: int
    status_changes: int
    diffs: list[StrategyDiff] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def impact_ratio(self) -> float:
        """Percentage of strategies affected by the policy change."""
        if self.total_strategies == 0:
            return 0.0
        return self.strategies_affected / self.total_strategies

    def to_dict(self) -> dict[str, Any]:
        return {
            "old_policy_version": self.old_policy_version,
            "new_policy_version": self.new_policy_version,
            "old_ruleset_hash": self.old_ruleset_hash,
            "new_ruleset_hash": self.new_ruleset_hash,
            "total_strategies": self.total_strategies,
            "strategies_affected": self.strategies_affected,
            "selection_changes": self.selection_changes,
            "stage_changes": self.stage_changes,
            "status_changes": self.status_changes,
            "impact_ratio": self.impact_ratio,
            "timestamp": self.timestamp,
            "diffs": [
                {
                    "strategy_id": d.strategy_id,
                    "selection_changed": d.selection_changed,
                    "stage_changed": d.stage_changed,
                    "status_changed": d.status_changed,
                    "old_selected": d.old_selected,
                    "new_selected": d.new_selected,
                    "old_recommended_stage": d.old_recommended_stage,
                    "new_recommended_stage": d.new_recommended_stage,
                    "old_status": d.old_status,
                    "new_status": d.new_status,
                    "rule_changes": d.rule_changes,
                }
                for d in self.diffs
                if d.has_changes
            ],
        }


def _load_policy(path: Path) -> Policy:
    """Load a policy from a YAML or JSON file."""
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = yaml.safe_load(raw)
    return parse_policy(data)


def _load_runs(path: Path) -> list[dict[str, Any]]:
    """Load evaluation runs from a JSON or YAML file."""
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = yaml.safe_load(raw)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "runs" in data:
        return data["runs"]
    raise ValueError(f"Expected a list of runs or a dict with 'runs' key in {path}")


def _extract_metrics(run: Mapping[str, Any]) -> dict[str, Any]:
    """Extract flat metrics from an EvaluationRun-like payload."""
    metrics = run.get("metrics", {})
    flat: dict[str, Any] = {}

    def visit(prefix: str, obj: Any) -> None:
        if isinstance(obj, Mapping):
            for k, v in obj.items():
                new_prefix = f"{prefix}.{k}" if prefix else k
                visit(new_prefix, v)
        elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
            # Store both dotted and leaf name
            flat[prefix] = obj
            leaf = prefix.split(".")[-1]
            flat.setdefault(leaf, obj)

    visit("", metrics)
    return flat


def _get_summary_status(result: PolicyEvaluationResult, strategy_id: str) -> str | None:
    """Derive overall status from rule results."""
    rules = result.rule_results.get(strategy_id, {})
    statuses = [r.status for r in rules.values()]
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    if statuses:
        return "pass"
    return None


def _compare_rule_results(
    old_result: PolicyEvaluationResult,
    new_result: PolicyEvaluationResult,
    strategy_id: str,
) -> list[dict[str, Any]]:
    """Compare rule results between old and new policy evaluation."""
    old_rules = old_result.rule_results.get(strategy_id, {})
    new_rules = new_result.rule_results.get(strategy_id, {})

    all_rule_names = set(old_rules.keys()) | set(new_rules.keys())
    changes: list[dict[str, Any]] = []

    for name in sorted(all_rule_names):
        old_rule = old_rules.get(name)
        new_rule = new_rules.get(name)

        old_status = old_rule.status if old_rule else None
        new_status = new_rule.status if new_rule else None

        if old_status != new_status:
            changes.append({
                "rule": name,
                "old_status": old_status,
                "new_status": new_status,
                "old_reason": old_rule.reason if old_rule else None,
                "new_reason": new_rule.reason if new_rule else None,
            })

    return changes


def compute_policy_diff(
    old_policy: Policy,
    new_policy: Policy,
    runs: Sequence[Mapping[str, Any]],
    *,
    stage: str | None = None,
    old_version: str | None = None,
    new_version: str | None = None,
) -> PolicyDiffReport:
    """Compute the diff between two policies over a set of evaluation runs.

    Args:
        old_policy: The current/baseline policy.
        new_policy: The proposed new policy.
        runs: List of EvaluationRun-like payloads with metrics.
        stage: Optional stage for profile selection.
        old_version: Optional version identifier for old policy.
        new_version: Optional version identifier for new policy.

    Returns:
        PolicyDiffReport with detailed per-strategy diffs.
    """
    # Build metrics map
    metrics_map: dict[str, dict[str, Any]] = {}
    for run in runs:
        strategy_id = run.get("strategy_id")
        if not strategy_id:
            continue
        metrics_map[str(strategy_id)] = _extract_metrics(run)

    if not metrics_map:
        return PolicyDiffReport(
            old_policy_version=old_version,
            new_policy_version=new_version,
            old_ruleset_hash=None,
            new_ruleset_hash=None,
            total_strategies=0,
            strategies_affected=0,
            selection_changes=0,
            stage_changes=0,
            status_changes=0,
        )

    # Evaluate both policies
    old_result = evaluate_policy(metrics_map, old_policy, stage=stage, policy_version=old_version)
    new_result = evaluate_policy(metrics_map, new_policy, stage=stage, policy_version=new_version)

    old_selected = set(old_result.selected_ids)
    new_selected = set(new_result.selected_ids)

    diffs: list[StrategyDiff] = []
    selection_changes = 0
    stage_changes = 0
    status_changes = 0

    for strategy_id in metrics_map:
        old_sel = strategy_id in old_selected
        new_sel = strategy_id in new_selected
        old_stage = old_result.recommended_stage
        new_stage = new_result.recommended_stage
        old_status = _get_summary_status(old_result, strategy_id)
        new_status = _get_summary_status(new_result, strategy_id)
        rule_changes = _compare_rule_results(old_result, new_result, strategy_id)

        diff = StrategyDiff(
            strategy_id=strategy_id,
            old_selected=old_sel,
            new_selected=new_sel,
            old_recommended_stage=old_stage,
            new_recommended_stage=new_stage,
            old_status=old_status,
            new_status=new_status,
            rule_changes=rule_changes,
        )

        if diff.selection_changed:
            selection_changes += 1
        if diff.stage_changed:
            stage_changes += 1
        if diff.status_changed:
            status_changes += 1

        diffs.append(diff)

    strategies_affected = sum(1 for d in diffs if d.has_changes)

    return PolicyDiffReport(
        old_policy_version=old_version or str(old_result.policy_version),
        new_policy_version=new_version or str(new_result.policy_version),
        old_ruleset_hash=old_result.ruleset_hash,
        new_ruleset_hash=new_result.ruleset_hash,
        total_strategies=len(metrics_map),
        strategies_affected=strategies_affected,
        selection_changes=selection_changes,
        stage_changes=stage_changes,
        status_changes=status_changes,
        diffs=diffs,
    )


def generate_markdown_report(report: PolicyDiffReport) -> str:
    """Generate a Markdown report from a PolicyDiffReport."""
    lines: list[str] = []

    lines.append("# Policy Diff Report")
    lines.append("")
    lines.append(f"**Generated**: {report.timestamp}")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Old Policy Version: `{report.old_policy_version or 'N/A'}`")
    lines.append(f"- New Policy Version: `{report.new_policy_version or 'N/A'}`")
    lines.append(f"- Old Ruleset Hash: `{report.old_ruleset_hash or 'N/A'}`")
    lines.append(f"- New Ruleset Hash: `{report.new_ruleset_hash or 'N/A'}`")
    lines.append("")
    lines.append(f"- Total Strategies: {report.total_strategies}")
    lines.append(f"- Strategies Affected: {report.strategies_affected}")
    lines.append(f"- Impact Ratio: {report.impact_ratio:.1%}")
    lines.append("")

    # Impact breakdown
    lines.append("## Impact Breakdown")
    lines.append("")
    lines.append(f"- Selection Changes: {report.selection_changes}")
    lines.append(f"- Stage Changes: {report.stage_changes}")
    lines.append(f"- Status Changes: {report.status_changes}")
    lines.append("")

    # Warning threshold
    if report.impact_ratio > 0.05:
        lines.append("> ⚠️ **Warning**: Impact ratio exceeds 5% threshold. Manual review recommended.")
        lines.append("")

    # Detailed diffs
    affected = [d for d in report.diffs if d.has_changes]
    if affected:
        lines.append("## Affected Strategies")
        lines.append("")
        lines.append("| Strategy | Selection | Stage | Status | Rule Changes |")
        lines.append("| --- | --- | --- | --- | --- |")

        for diff in affected:
            sel_change = ""
            if diff.selection_changed:
                sel_change = f"{'✓' if diff.old_selected else '✗'} → {'✓' if diff.new_selected else '✗'}"

            stage_change = ""
            if diff.stage_changed:
                stage_change = f"{diff.old_recommended_stage or 'N/A'} → {diff.new_recommended_stage or 'N/A'}"

            status_change = ""
            if diff.status_changed:
                status_change = f"{diff.old_status or 'N/A'} → {diff.new_status or 'N/A'}"

            rule_summary = f"{len(diff.rule_changes)} changes" if diff.rule_changes else "-"

            lines.append(f"| {diff.strategy_id} | {sel_change} | {stage_change} | {status_change} | {rule_summary} |")

        lines.append("")

        # Detailed rule changes
        lines.append("## Detailed Rule Changes")
        lines.append("")

        for diff in affected:
            if diff.rule_changes:
                lines.append(f"### {diff.strategy_id}")
                lines.append("")
                lines.append("| Rule | Old Status | New Status | Reason |")
                lines.append("| --- | --- | --- | --- |")

                for change in diff.rule_changes:
                    old_s = change.get("old_status") or "N/A"
                    new_s = change.get("new_status") or "N/A"
                    reason = change.get("new_reason") or change.get("old_reason") or ""
                    lines.append(f"| {change['rule']} | {old_s} | {new_s} | {reason} |")

                lines.append("")
    else:
        lines.append("## No Affected Strategies")
        lines.append("")
        lines.append("The policy change has no impact on the evaluated strategies.")
        lines.append("")

    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Compare the impact of policy changes on historical EvaluationRuns."
    )
    parser.add_argument(
        "--old",
        type=Path,
        required=True,
        help="Path to the old/baseline policy YAML/JSON file.",
    )
    parser.add_argument(
        "--new",
        type=Path,
        required=True,
        help="Path to the new/proposed policy YAML/JSON file.",
    )
    parser.add_argument(
        "--runs",
        type=Path,
        required=True,
        help="Path to the evaluation runs JSON/YAML file.",
    )
    parser.add_argument(
        "--stage",
        type=str,
        default=None,
        help="Optional stage for profile selection (e.g., backtest, paper).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output path for the Markdown report. If not specified, prints to stdout.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of Markdown.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.05,
        help="Impact ratio threshold for warning (default: 0.05 = 5%%).",
    )

    args = parser.parse_args(argv)

    try:
        old_policy = _load_policy(args.old)
        new_policy = _load_policy(args.new)
        runs = _load_runs(args.runs)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    report = compute_policy_diff(
        old_policy,
        new_policy,
        runs,
        stage=args.stage,
        old_version=str(args.old),
        new_version=str(args.new),
    )

    if args.json:
        output = json.dumps(report.to_dict(), indent=2)
    else:
        output = generate_markdown_report(report)

    if args.output:
        args.output.write_text(output, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(output)

    # Exit with error if impact exceeds threshold
    if report.impact_ratio > args.threshold:
        print(
            f"\nWarning: Impact ratio {report.impact_ratio:.1%} exceeds threshold {args.threshold:.1%}",
            file=sys.stderr,
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
