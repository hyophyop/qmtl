"""Backfill risk snapshots into PersistentStorage from current activation state."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict

import redis.asyncio as redis

from qmtl.services.worldservice.storage import PersistentStorage


def _iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


async def _backfill_world(storage: PersistentStorage, world_id: str, *, as_of: str) -> bool:
    try:
        decisions = await storage.get_decisions(world_id)
    except Exception:
        decisions = []
    if not decisions:
        return False
    weights: Dict[str, float] = {}
    try:
        snapshot = await storage.snapshot_activation(world_id)
        for sid, sides in (snapshot.state or {}).items():
            for entry in sides.values():
                if entry.get("active"):
                    weights[sid] = weights.get(sid, 0.0) + float(entry.get("weight", 1.0))
    except Exception:
        return False
    total = sum(weights.values())
    if total <= 0:
        return False
    normalized = {sid: w / total for sid, w in weights.items()}
    payload: Dict[str, Any] = {
        "world_id": world_id,
        "as_of": as_of,
        "version": f"backfill-{as_of}",
        "weights": normalized,
        "provenance": {"source": "backfill", "reason": "activation_snapshot"},
    }
    await storage.upsert_risk_snapshot(world_id, payload)
    return True


async def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill risk snapshots from activation state")
    parser.add_argument("--dsn", required=True, help="Database DSN for PersistentStorage")
    parser.add_argument("--redis", required=True, help="Redis DSN for activation cache")
    parser.add_argument("--world", action="append", help="Specific world id(s) to backfill")
    args = parser.parse_args()

    redis_client = redis.from_url(args.redis, decode_responses=True)
    storage = await PersistentStorage.create(db_dsn=args.dsn, redis_client=redis_client)
    as_of = _iso_now()
    targets = args.world
    if not targets:
        worlds = await storage.list_worlds()
        targets = [w["id"] for w in worlds]
    success = 0
    for wid in targets:
        ok = await _backfill_world(storage, wid, as_of=as_of)
        success += int(ok)
    await storage.close()
    print(f"Backfilled {success} snapshots")


if __name__ == "__main__":
    asyncio.run(main())
