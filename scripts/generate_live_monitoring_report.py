"""Generate a live monitoring report from stored EvaluationRuns.

Reads stage=live EvaluationRuns per world and renders a concise Markdown/JSON report.

Usage:
  WORLDS_DB_DSN=sqlite:///... WORLDS_REDIS_DSN=redis://... \\
    uv run python scripts/generate_live_monitoring_report.py --world w1 --output live_report.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as redis

from qmtl.services.worldservice.metrics import parse_timestamp
from qmtl.services.worldservice.storage import PersistentStorage


def _iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _latest_live_runs(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    live_runs = [r for r in runs if str(r.get("stage") or "").lower() == "live"]
    latest_by_strategy: dict[str, dict[str, Any]] = {}
    for run in live_runs:
        sid = str(run.get("strategy_id") or "")
        if not sid:
            continue
        ts = parse_timestamp(run.get("updated_at") or run.get("created_at"))
        prev = latest_by_strategy.get(sid)
        prev_ts = parse_timestamp(prev.get("updated_at") or prev.get("created_at")) if prev else None
        if prev is None or (ts and (prev_ts is None or ts > prev_ts)):
            latest_by_strategy[sid] = run
    return latest_by_strategy


def _render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# Live Monitoring Report — {report['world_id']}")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at']}")
    counts = (report.get("summary") or {}).get("counts") or {}
    lines.append(f"- Total strategies: {report.get('summary', {}).get('total', 0)}")
    lines.append(f"- Pass/Warn/Fail: {counts.get('pass',0)}/{counts.get('warn',0)}/{counts.get('fail',0)}")
    lines.append("")
    lines.append("| Strategy | Run ID | Status | live_sharpe_p30 | live_dd_p30 | decay_ratio | Reason |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for item in report.get("strategies", []):
        diag = item.get("diagnostics") or {}
        lm = item.get("live_monitoring") or {}
        status = str(lm.get("status") or "unknown").upper()
        reason = lm.get("reason") or lm.get("reason_code") or ""
        lines.append(
            "| {sid} | {rid} | {status} | {sharpe} | {dd} | {decay} | {reason} |".format(
                sid=item.get("strategy_id"),
                rid=item.get("run_id"),
                status=status,
                sharpe=diag.get("live_sharpe_p30"),
                dd=diag.get("live_max_drawdown_p30"),
                decay=diag.get("live_vs_backtest_sharpe_ratio"),
                reason=reason,
            )
        )
    return "\n".join(lines) + "\n"


async def _build_storage() -> tuple[PersistentStorage, Any]:
    dsn = os.environ.get("WORLDS_DB_DSN")
    redis_dsn = os.environ.get("WORLDS_REDIS_DSN")
    if not dsn or not redis_dsn:
        raise SystemExit("Missing WORLDS_DB_DSN/WORLDS_REDIS_DSN")
    redis_client = redis.from_url(redis_dsn, decode_responses=True)
    storage = await PersistentStorage.create(db_dsn=dsn, redis_client=redis_client)
    return storage, redis_client


async def main() -> None:
    parser = argparse.ArgumentParser(description="Generate live monitoring report")
    parser.add_argument("--world", action="append", help="world id(s); default=all")
    parser.add_argument("--format", choices=["md", "json"], default="md")
    parser.add_argument("--output", help="output path; default=stdout")
    args = parser.parse_args()

    storage, redis_client = await _build_storage()
    try:
        worlds = args.world
        if not worlds:
            worlds = [w["id"] for w in await storage.list_worlds() if w.get("id")]

        reports: list[dict[str, Any]] = []
        for wid in worlds:
            runs = await storage.list_evaluation_runs(world_id=wid)
            latest = _latest_live_runs(runs)
            strategies: list[dict[str, Any]] = []
            counts = {"pass": 0, "warn": 0, "fail": 0}
            for sid, run in sorted(latest.items()):
                metrics = run.get("metrics") if isinstance(run.get("metrics"), Mapping) else {}
                diagnostics = metrics.get("diagnostics") if isinstance(metrics.get("diagnostics"), Mapping) else {}
                validation = run.get("validation") if isinstance(run.get("validation"), Mapping) else {}
                results = validation.get("results") if isinstance(validation.get("results"), Mapping) else {}
                live_result = results.get("live_monitoring") if isinstance(results, Mapping) else None
                if isinstance(live_result, Mapping):
                    status = str(live_result.get("status") or "unknown")
                    if status in counts:
                        counts[status] += 1
                strategies.append(
                    {
                        "strategy_id": sid,
                        "run_id": run.get("run_id"),
                        "as_of": (run.get("summary") or {}).get("as_of"),
                        "diagnostics": dict(diagnostics) if isinstance(diagnostics, Mapping) else None,
                        "live_monitoring": dict(live_result) if isinstance(live_result, Mapping) else None,
                    }
                )
            reports.append(
                {
                    "world_id": wid,
                    "generated_at": _iso_now(),
                    "strategies": strategies,
                    "summary": {"counts": counts, "total": len(strategies)},
                }
            )

        if args.format == "json":
            output_text = json.dumps(reports if len(reports) > 1 else reports[0], indent=2)
        else:
            output_text = "\n".join(_render_markdown(r) for r in reports)

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output_text)
        else:
            print(output_text)
    finally:
        await storage.close()
        try:
            await redis_client.aclose()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())

