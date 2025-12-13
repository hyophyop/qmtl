"""Purge EvaluationRun history entries older than a retention cutoff.

Usage:
  WORLDS_DB_DSN=sqlite:///... WORLDS_REDIS_DSN=redis://... \\
    uv run python scripts/purge_evaluation_run_history.py --retention-days 180 --dry-run

  WORLDS_DB_DSN=... WORLDS_REDIS_DSN=... \\
    uv run python scripts/purge_evaluation_run_history.py --retention-days 180 --execute --output purge_report.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import redis.asyncio as redis

from qmtl.services.worldservice.storage import PersistentStorage


def _iso_utc(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


async def _build_storage() -> tuple[PersistentStorage, Any]:
    dsn = os.environ.get("WORLDS_DB_DSN")
    redis_dsn = os.environ.get("WORLDS_REDIS_DSN")
    if not dsn or not redis_dsn:
        raise SystemExit("Missing WORLDS_DB_DSN/WORLDS_REDIS_DSN")
    redis_client = redis.from_url(redis_dsn, decode_responses=True)
    storage = await PersistentStorage.create(db_dsn=dsn, redis_client=redis_client)
    return storage, redis_client


async def main() -> None:
    parser = argparse.ArgumentParser(description="Purge evaluation_run_history rows older than a cutoff")
    parser.add_argument("--world", action="append", help="world id(s); default=all")
    parser.add_argument("--retention-days", type=int, default=180)
    parser.add_argument("--older-than", help="override cutoff timestamp (ISO-8601, e.g. 2025-01-01T00:00:00Z)")
    parser.add_argument("--execute", action="store_true", help="actually delete rows (default: dry-run)")
    parser.add_argument("--vacuum", action="store_true", help="run VACUUM after deletion (sqlite only; best-effort)")
    parser.add_argument("--output", help="write JSON report to path (default: stdout)")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    older_than = args.older_than
    if not older_than:
        older_than = _iso_utc(now - timedelta(days=int(args.retention_days)))

    storage, redis_client = await _build_storage()
    try:
        worlds = args.world
        if not worlds:
            worlds = [w["id"] for w in await storage.list_worlds() if w.get("id")]

        per_world: list[dict[str, Any]] = []
        total_candidates = 0
        total_deleted = 0
        for wid in worlds:
            result = await storage.purge_evaluation_run_history(
                older_than=older_than,
                world_id=wid,
                dry_run=not args.execute,
                vacuum=bool(args.vacuum and args.execute),
            )
            per_world.append(dict(result))
            total_candidates += int(result.get("candidates") or 0)
            total_deleted += int(result.get("deleted") or 0)

        report = {
            "generated_at": _iso_utc(now),
            "older_than": older_than,
            "execute": bool(args.execute),
            "worlds": worlds,
            "summary": {
                "candidates": total_candidates,
                "deleted": total_deleted,
            },
            "results": per_world,
        }

        text = json.dumps(report, indent=2)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(text + "\n")
        else:
            print(text)
    finally:
        await storage.close()
        await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())

