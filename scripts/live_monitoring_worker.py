"""Cron/daemon worker to generate live monitoring EvaluationRuns.

This connects to PersistentStorage + Risk Signal Hub and periodically records
stage=live EvaluationRuns using realized returns from hub snapshots.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from typing import Any

import redis.asyncio as redis

from qmtl.services.worldservice.blob_store import build_blob_store
from qmtl.services.worldservice.live_monitoring_worker import LiveMonitoringWorker
from qmtl.services.worldservice.risk_hub import RiskSignalHub
from qmtl.services.worldservice.storage import PersistentStorage


async def _build_storage() -> PersistentStorage:
    dsn = os.environ.get("WORLDS_DB_DSN")
    redis_dsn = os.environ.get("WORLDS_REDIS_DSN")
    if not dsn or not redis_dsn:
        raise SystemExit("Missing WORLDS_DB_DSN/WORLDS_REDIS_DSN")
    redis_client = redis.from_url(redis_dsn, decode_responses=True)
    storage = await PersistentStorage.create(db_dsn=dsn, redis_client=redis_client)
    storage._redis_client = redis_client  # type: ignore[attr-defined]
    return storage


async def main() -> None:
    parser = argparse.ArgumentParser(description="Live monitoring EvaluationRun generator")
    parser.add_argument("--world", action="append", help="world id(s) to refresh; default=all")
    parser.add_argument("--interval-seconds", type=float, default=0.0, help="run loop interval; 0=once")
    parser.add_argument("--blob-store-type", default="file", help="blob store type for refs (file|redis|s3)")
    parser.add_argument("--blob-store-base-dir", default=".risk_blobs", help="base dir for file blob store")
    parser.add_argument("--blob-store-bucket", help="bucket for s3 blob store")
    parser.add_argument("--blob-store-prefix", help="prefix for s3 blob store")
    parser.add_argument("--inline-cov-threshold", type=int, default=100, help="inline covariance threshold")
    args = parser.parse_args()

    storage = await _build_storage()
    redis_client = getattr(storage, "_redis_client", None)

    blob_store = None
    try:
        blob_store = build_blob_store(
            store_type=args.blob_store_type,
            base_dir=args.blob_store_base_dir,
            bucket=args.blob_store_bucket,
            prefix=args.blob_store_prefix,
            redis_client=None,
            redis_dsn=os.environ.get("WORLDS_REDIS_DSN"),
        )
    except Exception:
        blob_store = None

    hub = RiskSignalHub(
        repository=getattr(storage, "risk_snapshots", None),
        cache=redis_client,
        blob_store=blob_store,
        inline_cov_threshold=args.inline_cov_threshold,
    )

    worker = LiveMonitoringWorker(storage, risk_hub=hub)

    async def _run_once() -> None:
        if args.world:
            for wid in args.world:
                await worker.run_world(wid)
        else:
            await worker.run_all_worlds()

    try:
        if args.interval_seconds and args.interval_seconds > 0:
            while True:
                await _run_once()
                await asyncio.sleep(args.interval_seconds)
        else:
            await _run_once()
    finally:
        try:
            await storage.close()
        except Exception:
            pass
        if redis_client is not None:
            try:
                await redis_client.aclose()
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())

