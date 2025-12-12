"""Publish Risk Signal Hub snapshots from external producers.

This script standardizes producer-side validation/offload rules for
realized returns, stress metrics, and covariance payloads.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any, Sequence

from qmtl.services.gateway.risk_hub_client import RiskHubClient
from qmtl.services.risk_hub_contract import normalize_and_validate_snapshot
from qmtl.services.worldservice.blob_store import build_blob_store


def _env_default(key: str, fallback: str | None = None) -> str | None:
    val = os.environ.get(key)
    return val if val not in (None, "") else fallback


def _parse_allowlist(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    items = [p.strip() for p in raw.split(",") if p.strip()]
    return items or None


async def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Publish a risk hub snapshot")
    parser.add_argument("--base-url", required=True, help="WorldService base URL")
    parser.add_argument("--world", required=True, help="world id to publish")
    parser.add_argument("--snapshot", required=True, help="Path to snapshot JSON payload")
    parser.add_argument("--token", help="Bearer token for risk hub router")
    parser.add_argument("--actor", default=_env_default("RISK_HUB_ACTOR", "risk-engine"))
    parser.add_argument("--stage", default=_env_default("RISK_HUB_STAGE"))
    parser.add_argument("--ttl-sec", type=int, default=int(_env_default("RISK_HUB_TTL_SEC", "10") or 10))
    parser.add_argument("--inline-threshold", type=int, default=int(_env_default("RISK_HUB_INLINE_THRESHOLD", "100") or 100))
    parser.add_argument("--retries", type=int, default=int(_env_default("RISK_HUB_RETRIES", "2") or 2))
    parser.add_argument("--backoff", type=float, default=float(_env_default("RISK_HUB_BACKOFF", "0.5") or 0.5))
    parser.add_argument("--timeout", type=float, default=float(_env_default("RISK_HUB_TIMEOUT", "5.0") or 5.0))

    parser.add_argument("--blob-type", default=_env_default("RISK_HUB_BLOB_TYPE", "file"))
    parser.add_argument("--blob-base-dir", default=_env_default("RISK_HUB_BLOB_BASE_DIR", ".risk_blobs"))
    parser.add_argument("--blob-bucket", default=_env_default("RISK_HUB_BLOB_BUCKET"))
    parser.add_argument("--blob-prefix", default=_env_default("RISK_HUB_BLOB_PREFIX"))
    parser.add_argument("--blob-redis-dsn", default=_env_default("RISK_HUB_BLOB_REDIS_DSN"))
    parser.add_argument("--blob-redis-prefix", default=_env_default("RISK_HUB_BLOB_REDIS_PREFIX"))
    parser.add_argument("--blob-cache-ttl", type=int, default=None)

    parser.add_argument("--allowed-actors", help="Comma-separated actor allowlist")
    parser.add_argument("--allowed-stages", help="Comma-separated stage allowlist")

    args = parser.parse_args(argv)

    payload: Any = json.loads(Path(args.snapshot).read_text())
    if not isinstance(payload, dict):
        raise SystemExit("snapshot payload must be a JSON object")

    allowed_actors = _parse_allowlist(args.allowed_actors)
    allowed_stages = _parse_allowlist(args.allowed_stages)

    validated = normalize_and_validate_snapshot(
        args.world,
        payload,
        actor=args.actor,
        stage=args.stage,
        ttl_sec_default=args.ttl_sec,
        allowed_actors=allowed_actors,
        allowed_stages=allowed_stages,
    )

    blob_store = build_blob_store(
        store_type=str(args.blob_type),
        base_dir=args.blob_base_dir,
        bucket=args.blob_bucket,
        prefix=args.blob_prefix,
        redis_dsn=args.blob_redis_dsn,
        redis_prefix=args.blob_redis_prefix,
        cache_ttl=args.blob_cache_ttl,
    )

    client = RiskHubClient(
        base_url=args.base_url,
        timeout=args.timeout,
        retries=args.retries,
        backoff=args.backoff,
        auth_token=args.token,
        blob_store=blob_store,
        inline_cov_threshold=args.inline_threshold,
        actor=args.actor or "risk-engine",
        stage=args.stage,
        ttl_sec=args.ttl_sec,
    )

    result = await client.publish_snapshot(args.world, validated)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())

