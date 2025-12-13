#!/usr/bin/env python3
"""Scenario SLO guardrails for policy snapshots.

This tool consumes a JSON snapshot produced by ``scripts/policy_snapshot.py`` and
enforces simple ratio-based constraints (e.g., good set should have 0 fails).

Intended for CI gating on validation policy/rule changes.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class ScenarioSummary:
    total: int
    passed: int
    warned: int
    failed: int
    unknown: int

    @property
    def pass_ratio(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def warn_ratio(self) -> float:
        return self.warned / self.total if self.total else 0.0

    @property
    def fail_ratio(self) -> float:
        return self.failed / self.total if self.total else 0.0

    @property
    def unknown_ratio(self) -> float:
        return self.unknown / self.total if self.total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "warned": self.warned,
            "failed": self.failed,
            "unknown": self.unknown,
            "pass_ratio": self.pass_ratio,
            "warn_ratio": self.warn_ratio,
            "fail_ratio": self.fail_ratio,
            "unknown_ratio": self.unknown_ratio,
        }


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_snapshot(snapshot: Mapping[str, Any]) -> ScenarioSummary:
    strategies = snapshot.get("strategies") if isinstance(snapshot.get("strategies"), Mapping) else {}
    passed = warned = failed = unknown = 0
    for entry in strategies.values():
        status = entry.get("status") if isinstance(entry, Mapping) else None
        if status == "pass":
            passed += 1
        elif status == "warn":
            warned += 1
        elif status == "fail":
            failed += 1
        else:
            unknown += 1
    total = len(strategies)
    return ScenarioSummary(total=total, passed=passed, warned=warned, failed=failed, unknown=unknown)


def _check_ratio(name: str, value: float, *, min_value: float | None, max_value: float | None) -> list[str]:
    errors: list[str] = []
    if min_value is not None and value < min_value:
        errors.append(f"{name} {value:.3f} < min {min_value:.3f}")
    if max_value is not None and value > max_value:
        errors.append(f"{name} {value:.3f} > max {max_value:.3f}")
    return errors


def check_snapshot(
    snapshot: Mapping[str, Any],
    *,
    min_pass_ratio: float | None,
    max_pass_ratio: float | None,
    min_warn_ratio: float | None,
    max_warn_ratio: float | None,
    min_fail_ratio: float | None,
    max_fail_ratio: float | None,
    min_unknown_ratio: float | None,
    max_unknown_ratio: float | None,
) -> tuple[ScenarioSummary, list[str]]:
    summary = summarize_snapshot(snapshot)
    errors: list[str] = []
    errors.extend(_check_ratio("pass_ratio", summary.pass_ratio, min_value=min_pass_ratio, max_value=max_pass_ratio))
    errors.extend(_check_ratio("warn_ratio", summary.warn_ratio, min_value=min_warn_ratio, max_value=max_warn_ratio))
    errors.extend(_check_ratio("fail_ratio", summary.fail_ratio, min_value=min_fail_ratio, max_value=max_fail_ratio))
    errors.extend(
        _check_ratio(
            "unknown_ratio",
            summary.unknown_ratio,
            min_value=min_unknown_ratio,
            max_value=max_unknown_ratio,
        )
    )
    return summary, errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Enforce ratio-based SLO constraints over a policy snapshot.")
    parser.add_argument("--snapshot", required=True, type=Path, help="Snapshot JSON produced by policy_snapshot.py")
    parser.add_argument("--output", type=Path, default=None, help="Optional output path for summary JSON")
    parser.add_argument("--min-pass-ratio", type=float, default=None)
    parser.add_argument("--max-pass-ratio", type=float, default=None)
    parser.add_argument("--min-warn-ratio", type=float, default=None)
    parser.add_argument("--max-warn-ratio", type=float, default=None)
    parser.add_argument("--min-fail-ratio", type=float, default=None)
    parser.add_argument("--max-fail-ratio", type=float, default=None)
    parser.add_argument("--min-unknown-ratio", type=float, default=None)
    parser.add_argument("--max-unknown-ratio", type=float, default=None)
    args = parser.parse_args()

    snapshot = _load_json(args.snapshot)
    summary, errors = check_snapshot(
        snapshot,
        min_pass_ratio=args.min_pass_ratio,
        max_pass_ratio=args.max_pass_ratio,
        min_warn_ratio=args.min_warn_ratio,
        max_warn_ratio=args.max_warn_ratio,
        min_fail_ratio=args.min_fail_ratio,
        max_fail_ratio=args.max_fail_ratio,
        min_unknown_ratio=args.min_unknown_ratio,
        max_unknown_ratio=args.max_unknown_ratio,
    )
    payload = summary.to_dict()
    if args.output is not None:
        args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if errors:
        raise SystemExit("Scenario SLO check failed: " + "; ".join(errors))


if __name__ == "__main__":
    main()
