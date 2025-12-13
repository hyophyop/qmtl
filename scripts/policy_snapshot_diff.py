#!/usr/bin/env python3
"""Policy snapshot diff tool.

Compares two policy snapshots (base vs head) and emits a JSON/Markdown report.
Designed for CI gating of validation policy/rule changes.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


@dataclass
class StrategySnapshotDiff:
    strategy_id: str
    old_selected: bool | None
    new_selected: bool | None
    old_status: str | None
    new_status: str | None
    old_recommended_stage: str | None
    new_recommended_stage: str | None
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
class PolicySnapshotDiffReport:
    old_revision: str | None
    new_revision: str | None
    old_policy_version: str | None
    new_policy_version: str | None
    old_ruleset_hash: str | None
    new_ruleset_hash: str | None
    total_strategies: int
    strategies_affected: int
    selection_changes: int
    stage_changes: int
    status_changes: int
    rule_status_changes: int
    diffs: list[StrategySnapshotDiff] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def impact_ratio(self) -> float:
        if self.total_strategies == 0:
            return 0.0
        return self.strategies_affected / self.total_strategies

    def to_dict(self) -> dict[str, Any]:
        return {
            "old_revision": self.old_revision,
            "new_revision": self.new_revision,
            "old_policy_version": self.old_policy_version,
            "new_policy_version": self.new_policy_version,
            "old_ruleset_hash": self.old_ruleset_hash,
            "new_ruleset_hash": self.new_ruleset_hash,
            "total_strategies": self.total_strategies,
            "strategies_affected": self.strategies_affected,
            "selection_changes": self.selection_changes,
            "stage_changes": self.stage_changes,
            "status_changes": self.status_changes,
            "rule_status_changes": self.rule_status_changes,
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
                    "old_status": d.old_status,
                    "new_status": d.new_status,
                    "old_recommended_stage": d.old_recommended_stage,
                    "new_recommended_stage": d.new_recommended_stage,
                    "rule_changes": d.rule_changes,
                }
                for d in self.diffs
                if d.has_changes
            ],
        }


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _compare_rule_results(old_rules: Mapping[str, Any], new_rules: Mapping[str, Any]) -> tuple[list[dict[str, Any]], int]:
    all_names = set(old_rules.keys()) | set(new_rules.keys())
    changes: list[dict[str, Any]] = []
    change_count = 0
    for name in sorted(all_names):
        old = old_rules.get(name) or {}
        new = new_rules.get(name) or {}
        old_status = old.get("status")
        new_status = new.get("status")
        if old_status != new_status:
            change_count += 1
            changes.append({
                "rule": name,
                "old_status": old_status,
                "new_status": new_status,
                "old_reason_code": old.get("reason_code"),
                "new_reason_code": new.get("reason_code"),
                "old_reason": old.get("reason"),
                "new_reason": new.get("reason"),
            })
    return changes, change_count


def diff_snapshots(old_snapshot: Mapping[str, Any], new_snapshot: Mapping[str, Any]) -> PolicySnapshotDiffReport:
    old_strategies = old_snapshot.get("strategies") or {}
    new_strategies = new_snapshot.get("strategies") or {}
    all_ids = sorted(set(old_strategies.keys()) | set(new_strategies.keys()))

    old_stage = old_snapshot.get("recommended_stage")
    new_stage = new_snapshot.get("recommended_stage")

    diffs: list[StrategySnapshotDiff] = []
    selection_changes = stage_changes = status_changes = 0
    rule_status_changes = 0

    for strategy_id in all_ids:
        old_entry = old_strategies.get(strategy_id) or {}
        new_entry = new_strategies.get(strategy_id) or {}

        old_selected = old_entry.get("selected")
        new_selected = new_entry.get("selected")
        old_status = old_entry.get("status")
        new_status = new_entry.get("status")

        rule_changes, rule_change_count = _compare_rule_results(
            old_entry.get("rule_results") or {},
            new_entry.get("rule_results") or {},
        )
        rule_status_changes += rule_change_count

        diff = StrategySnapshotDiff(
            strategy_id=strategy_id,
            old_selected=old_selected,
            new_selected=new_selected,
            old_status=old_status,
            new_status=new_status,
            old_recommended_stage=old_stage,
            new_recommended_stage=new_stage,
            rule_changes=rule_changes,
        )
        if diff.selection_changed:
            selection_changes += 1
        if diff.stage_changed:
            stage_changes += 1
        if diff.status_changed:
            status_changes += 1
        diffs.append(diff)

    affected = [d for d in diffs if d.has_changes]
    return PolicySnapshotDiffReport(
        old_revision=old_snapshot.get("revision"),
        new_revision=new_snapshot.get("revision"),
        old_policy_version=old_snapshot.get("policy_version"),
        new_policy_version=new_snapshot.get("policy_version"),
        old_ruleset_hash=old_snapshot.get("ruleset_hash"),
        new_ruleset_hash=new_snapshot.get("ruleset_hash"),
        total_strategies=len(all_ids),
        strategies_affected=len(affected),
        selection_changes=selection_changes,
        stage_changes=stage_changes,
        status_changes=status_changes,
        rule_status_changes=rule_status_changes,
        diffs=affected,
    )


def generate_markdown_report(report: PolicySnapshotDiffReport) -> str:
    lines: list[str] = []
    lines.append("# Policy Regression Report (Snapshot Diff)")
    lines.append("")
    lines.append(f"**Generated**: {report.timestamp}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Old Revision: `{report.old_revision or 'N/A'}`")
    lines.append(f"- New Revision: `{report.new_revision or 'N/A'}`")
    lines.append(f"- Old Policy Version: `{report.old_policy_version or 'N/A'}`")
    lines.append(f"- New Policy Version: `{report.new_policy_version or 'N/A'}`")
    lines.append(f"- Old Ruleset Hash: `{report.old_ruleset_hash or 'N/A'}`")
    lines.append(f"- New Ruleset Hash: `{report.new_ruleset_hash or 'N/A'}`")
    lines.append("")
    lines.append(f"- Total Strategies: {report.total_strategies}")
    lines.append(f"- Strategies Affected: {report.strategies_affected}")
    lines.append(f"- Impact Ratio: {report.impact_ratio:.1%}")
    lines.append("")
    lines.append("## Impact Breakdown")
    lines.append("")
    lines.append(f"- Selection Changes: {report.selection_changes}")
    lines.append(f"- Stage Changes: {report.stage_changes}")
    lines.append(f"- Status Changes: {report.status_changes}")
    lines.append(f"- Rule Status Changes: {report.rule_status_changes}")
    lines.append("")

    if report.diffs:
        lines.append("## Affected Strategies")
        lines.append("")
        lines.append("| Strategy | Selection | Status | Rule Changes |")
        lines.append("| --- | --- | --- | --- |")
        for diff in report.diffs:
            sel = ""
            if diff.selection_changed:
                sel = f"{diff.old_selected} → {diff.new_selected}"
            status = ""
            if diff.status_changed:
                status = f"{diff.old_status or 'N/A'} → {diff.new_status or 'N/A'}"
            rule_summary = f"{len(diff.rule_changes)} changes" if diff.rule_changes else "-"
            lines.append(f"| {diff.strategy_id} | {sel} | {status} | {rule_summary} |")
        lines.append("")
    else:
        lines.append("## No Affected Strategies")
        lines.append("")
        lines.append("No strategies were affected by the change under the selected scenario set.")
        lines.append("")

    return "\n".join(lines)


def run_diff(
    *,
    old: Path,
    new: Path,
    output: Path,
    output_md: Path | None,
    fail_impact_ratio: float | None,
) -> PolicySnapshotDiffReport:
    old_snapshot = _load_json(old)
    new_snapshot = _load_json(new)
    report = diff_snapshots(old_snapshot, new_snapshot)
    output.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    if output_md is not None:
        output_md.write_text(generate_markdown_report(report), encoding="utf-8")
    if fail_impact_ratio is not None and report.impact_ratio >= fail_impact_ratio:
        raise SystemExit(f"Impact ratio {report.impact_ratio:.2f} exceeds threshold {fail_impact_ratio}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two policy snapshots and emit a regression report.")
    parser.add_argument("--old", required=True, type=Path, help="Old/base policy snapshot JSON")
    parser.add_argument("--new", required=True, type=Path, help="New/head policy snapshot JSON")
    parser.add_argument("--output", type=Path, default=Path("policy_regression_report.json"), help="Output JSON path")
    parser.add_argument("--output-md", type=Path, default=None, help="Optional Markdown report output path")
    parser.add_argument("--fail-impact-ratio", type=float, default=None, help="Fail if impacted ratio >= threshold (0~1)")
    args = parser.parse_args()

    run_diff(
        old=args.old,
        new=args.new,
        output=args.output,
        output_md=args.output_md,
        fail_impact_ratio=args.fail_impact_ratio,
    )


if __name__ == "__main__":
    main()
