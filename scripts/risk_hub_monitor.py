"""Simple monitoring script for Risk Signal Hub freshness/health."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from typing import Dict, List

import httpx


def _iso_now() -> datetime:
    return datetime.now(timezone.utc)


async def fetch_latest(base_url: str, world_id: str, token: str | None, timeout: float) -> Dict:
    headers = {"Authorization": f"Bearer {token}"} if token else None
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(
            f"{base_url.rstrip('/')}/risk-hub/worlds/{world_id}/snapshots/latest",
            headers=headers,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"{world_id}: {resp.status_code} {resp.text}")
        return resp.json()


def _lag_seconds(as_of: str) -> float:
    text = as_of
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    ts = datetime.fromisoformat(text)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (_iso_now() - ts).total_seconds()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Risk hub freshness monitor")
    parser.add_argument("--base-url", required=True, help="WorldService base URL")
    parser.add_argument("--world", action="append", required=True, help="world id(s) to check")
    parser.add_argument("--token", help="Bearer token for risk hub")
    parser.add_argument("--warn-seconds", type=int, default=600, help="freshness warning threshold")
    parser.add_argument("--timeout", type=float, default=5.0, help="HTTP timeout seconds")
    args = parser.parse_args()

    worlds: List[str] = args.world
    warn = args.warn_seconds
    failures = 0
    for wid in worlds:
        try:
            snap = await fetch_latest(args.base_url, wid, args.token, args.timeout)
            lag = _lag_seconds(snap["as_of"])
            if lag > warn:
                print(f"WARNING {wid}: lag={lag:.0f}s as_of={snap['as_of']}")
            else:
                print(f"OK {wid}: lag={lag:.0f}s")
        except Exception as exc:
            failures += 1
            print(f"ERROR {wid}: {exc}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
