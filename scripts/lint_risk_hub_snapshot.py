"""Lint Risk Signal Hub snapshot payloads for contract compliance."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from qmtl.services.risk_hub_contract import normalize_and_validate_snapshot


def _parse_allowlist(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    items = [p.strip() for p in raw.split(",") if p.strip()]
    return items or None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint risk hub snapshot JSON files")
    parser.add_argument("snapshots", nargs="+", help="Path(s) to snapshot JSON files")
    parser.add_argument("--world", help="Override world_id (otherwise read from payload)")
    parser.add_argument("--actor", help="Actor to validate/inject into provenance")
    parser.add_argument("--stage", help="Stage to validate/inject into provenance")
    parser.add_argument("--ttl-sec", type=int, default=10, help="Default TTL when missing")
    parser.add_argument("--allowed-actors", help="Comma-separated actor allowlist")
    parser.add_argument("--allowed-stages", help="Comma-separated stage allowlist")
    args = parser.parse_args(argv)

    allowed_actors = _parse_allowlist(args.allowed_actors)
    allowed_stages = _parse_allowlist(args.allowed_stages)

    failures = 0
    for item in args.snapshots:
        path = Path(item)
        try:
            payload: Any = json.loads(path.read_text())
            if not isinstance(payload, dict):
                raise ValueError("payload must be a JSON object")
            wid = args.world or str(payload.get("world_id") or "")
            normalize_and_validate_snapshot(
                wid,
                payload,
                actor=args.actor,
                stage=args.stage,
                ttl_sec_default=args.ttl_sec,
                allowed_actors=allowed_actors,
                allowed_stages=allowed_stages,
            )
            print(f"OK {path}")
        except Exception as exc:
            failures += 1
            sys.stderr.write(f"ERROR {path}: {exc}\n")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

