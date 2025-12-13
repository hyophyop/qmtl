"""Generate an override re-review queue report from stored EvaluationRuns.

This script aggregates Invariant 3 ("approved override management") signals across
worlds and renders a concise Markdown/JSON report for operations.

Usage:
  WORLDS_DB_DSN=sqlite:///... WORLDS_REDIS_DSN=redis://... \\
    uv run python scripts/generate_override_rereview_report.py --output override_queue.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as redis

from qmtl.services.worldservice.storage import PersistentStorage
from qmtl.services.worldservice.validation_checks import check_validation_invariants


def _iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Override Re-review Queue")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at']}")
    lines.append(f"- Worlds scanned: {report['summary'].get('worlds_scanned', 0)}")
    lines.append(f"- Overrides found: {report['summary'].get('overrides_total', 0)}")
    lines.append(f"- Overdue overrides: {report['summary'].get('overrides_overdue', 0)}")
    lines.append("")

    lines.append(
        "| World | Strategy | Run ID | Stage | Override at | Due at | Overdue | Missing fields | Reason |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for item in report.get("overrides", []):
        missing = item.get("missing_fields") or []
        lines.append(
            "| {world} | {strategy} | {run_id} | {stage} | {ts} | {due} | {overdue} | {missing} | {reason} |".format(
                world=item.get("world_id", ""),
                strategy=item.get("strategy_id", ""),
                run_id=item.get("run_id", ""),
                stage=item.get("stage", ""),
                ts=item.get("override_timestamp") or "",
                due=item.get("review_due_at") or "",
                overdue=str(bool(item.get("review_overdue"))).lower()
                if item.get("review_overdue") is not None
                else "",
                missing=",".join(str(m) for m in missing) if missing else "",
                reason=item.get("override_reason") or "",
            )
        )
    return "\n".join(lines).strip() + "\n"


async def _build_storage() -> tuple[PersistentStorage, Any]:
    dsn = os.environ.get("WORLDS_DB_DSN")
    redis_dsn = os.environ.get("WORLDS_REDIS_DSN")
    if not dsn or not redis_dsn:
        raise SystemExit("Missing WORLDS_DB_DSN/WORLDS_REDIS_DSN")
    redis_client = redis.from_url(redis_dsn, decode_responses=True)
    storage = await PersistentStorage.create(db_dsn=dsn, redis_client=redis_client)
    return storage, redis_client


async def main() -> None:
    parser = argparse.ArgumentParser(description="Generate override re-review queue report")
    parser.add_argument("--world", action="append", help="world id(s); default=all")
    parser.add_argument("--format", choices=["md", "json"], default="md")
    parser.add_argument("--output", help="output path; default=stdout")
    args = parser.parse_args()

    storage, redis_client = await _build_storage()
    try:
        worlds = args.world
        if not worlds:
            worlds = [w["id"] for w in await storage.list_worlds() if w.get("id")]

        overrides: list[dict[str, Any]] = []
        overdue_count = 0
        for wid in worlds:
            world = await storage.get_world(wid) or {"id": wid}
            runs = await storage.list_evaluation_runs(world_id=wid)
            report = check_validation_invariants(world, runs)
            for item in report.approved_overrides:
                overrides.append(dict(item))
                if item.get("review_overdue") is True:
                    overdue_count += 1

        report_payload = {
            "generated_at": _iso_now(),
            "summary": {
                "worlds_scanned": len(worlds),
                "overrides_total": len(overrides),
                "overrides_overdue": overdue_count,
            },
            "overrides": overrides,
        }

        if args.format == "json":
            output_text = json.dumps(report_payload, indent=2)
        else:
            output_text = _render_markdown(report_payload)

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

