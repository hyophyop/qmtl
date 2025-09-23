from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List
import sys

from qmtl.runtime.transforms.alpha_performance import alpha_performance_node


def _build_report(metrics: dict[str, float]) -> str:
    """Build a markdown report from metrics."""
    lines = ["# Backtest Report", ""]
    for key, value in metrics.items():
        pretty = key.replace("_", " ").title()
        if isinstance(value, float):
            lines.append(f"- **{pretty}**: {value:.6f}")
        else:
            lines.append(f"- **{pretty}**: {value}")
    lines.append("")
    return "\n".join(lines)


def run(argv: List[str] | None = None) -> None:
    """Entrypoint for ``qmtl tools report`` subcommand."""
    parser = argparse.ArgumentParser(prog="qmtl tools report", description="Generate performance report from results.json")
    parser.add_argument("--from", dest="input", required=True, help="Path to results JSON containing a 'returns' array")
    parser.add_argument("--out", dest="output", default="report.md", help="Output markdown file path")
    parser.add_argument("--risk-free", dest="risk_free", type=float, default=0.0, help="Risk free rate")
    parser.add_argument("--transaction-cost", dest="transaction_cost", type=float, default=0.0, help="Transaction cost per period")
    args = parser.parse_args(argv)

    try:
        text = Path(args.input).read_text()
    except OSError as e:
        print(f"Failed to read input file '{args.input}': {e}", file=sys.stderr)
        raise SystemExit(1)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in '{args.input}': {e}", file=sys.stderr)
        raise SystemExit(1)

    returns = data.get("returns")
    if returns is None:
        print("Input JSON must contain a 'returns' key", file=sys.stderr)
        raise SystemExit(1)

    metrics = alpha_performance_node(returns, risk_free_rate=args.risk_free, transaction_cost=args.transaction_cost)
    report_md = _build_report(metrics)
    Path(args.output).write_text(report_md)
