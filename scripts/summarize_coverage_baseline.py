#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_FOCUS_PREFIXES = (
    "qmtl/runtime/sdk/",
    "qmtl/runtime/pipeline/",
    "qmtl/services/gateway/",
)
SUMMARY_KEYS = (
    "covered_lines",
    "num_statements",
    "missing_lines",
    "excluded_lines",
    "covered_branches",
    "num_branches",
    "missing_branches",
    "num_partial_branches",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize branch-coverage baselines from coverage.py JSON output."
    )
    parser.add_argument("--input", required=True, help="Path to coverage JSON report.")
    parser.add_argument("--json-output", required=True, help="Where to write the summary JSON.")
    parser.add_argument(
        "--markdown-output",
        required=True,
        help="Where to write the Markdown summary.",
    )
    parser.add_argument(
        "--focus-prefix",
        action="append",
        dest="focus_prefixes",
        help="Path prefix to summarize separately. Can be provided multiple times.",
    )
    return parser.parse_args()


def _empty_summary() -> dict[str, int]:
    return {key: 0 for key in SUMMARY_KEYS}


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def _merge_summary(target: dict[str, int], source: dict[str, Any]) -> None:
    for key in SUMMARY_KEYS:
        target[key] += int(source.get(key, 0))


def _percent(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round((numerator / denominator) * 100, 2)


def _finalize(summary: dict[str, int]) -> dict[str, Any]:
    return {
        **summary,
        "line_percent": _percent(summary["covered_lines"], summary["num_statements"]),
        "branch_percent": _percent(summary["covered_branches"], summary["num_branches"]),
    }


def _aggregate_focus_areas(
    files: dict[str, Any], focus_prefixes: tuple[str, ...]
) -> dict[str, dict[str, Any]]:
    focus_areas: dict[str, dict[str, Any]] = {}
    for prefix in focus_prefixes:
        aggregate = _empty_summary()
        matched_files = 0
        for path, payload in files.items():
            if _normalize_path(path).startswith(prefix):
                matched_files += 1
                _merge_summary(aggregate, payload.get("summary", {}))
        focus_areas[prefix] = {
            "file_count": matched_files,
            **_finalize(aggregate),
        }
    return focus_areas


def _write_markdown(
    markdown_output: Path,
    overall: dict[str, Any],
    focus_areas: dict[str, dict[str, Any]],
) -> None:
    def fmt_percent(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.2f}%"

    lines = [
        "# Branch Coverage Baseline",
        "",
        "| Area | Files | Line coverage | Branch coverage | Covered branches | Total branches |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        (
            f"| qmtl (overall) | {overall.get('file_count', 'n/a')} | "
            f"{fmt_percent(overall['line_percent'])} | {fmt_percent(overall['branch_percent'])} | "
            f"{overall['covered_branches']} | {overall['num_branches']} |"
        ),
    ]

    for prefix, summary in focus_areas.items():
        lines.append(
            f"| `{prefix}` | {summary['file_count']} | "
            f"{fmt_percent(summary['line_percent'])} | {fmt_percent(summary['branch_percent'])} | "
            f"{summary['covered_branches']} | {summary['num_branches']} |"
        )

    lines.extend(
        [
            "",
            "Current rollout stage: report-only branch-coverage baseline collection.",
            "Promotion to a hard gate requires stable overall and focus-area baselines plus documented thresholds.",
        ]
    )
    markdown_output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = _parse_args()
    input_path = Path(args.input)
    json_output = Path(args.json_output)
    markdown_output = Path(args.markdown_output)

    coverage_report = json.loads(input_path.read_text(encoding="utf-8"))
    files = coverage_report.get("files", {})
    totals = dict(coverage_report.get("totals", {}))
    overall = _finalize(
        {
            key: int(totals.get(key, 0))
            for key in SUMMARY_KEYS
        }
    )
    overall["file_count"] = len(files)

    focus_prefixes = tuple(args.focus_prefixes or DEFAULT_FOCUS_PREFIXES)
    focus_areas = _aggregate_focus_areas(files, focus_prefixes)

    payload = {
        "overall": overall,
        "focus_areas": focus_areas,
        "focus_prefixes": list(focus_prefixes),
    }
    json_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_markdown(markdown_output=markdown_output, overall=overall, focus_areas=focus_areas)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
