"""Demonstrate a 2-phase apply request with gating policy data.

The script loads the example gating policy, attaches dummy evaluation
metrics, and posts the payload to a WorldService instance. Use it to
exercise the new gating hooks locally after spinning up Gateway and
WorldService (e.g., ``uv run uvicorn qmtl.services.worldservice.api:create_app --factory``)
or via Docker Compose.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Mapping

import httpx

from qmtl.services.worldservice.policy import parse_gating_policy


_DEFAULT_POLICY_PATH = (
    Path(__file__).resolve().parents[1] / "worldservice" / "gating_policy.example.yml"
)


def _load_gating_policy(path: Path) -> Mapping[str, Any]:
    """Return the parsed gating policy payload."""

    data = path.read_text(encoding="utf-8")
    policy = parse_gating_policy(data)
    return policy.model_dump()


def _build_metrics(strategy_ids: list[str]) -> dict[str, dict[str, float]]:
    """Create placeholder metrics satisfying the apply endpoint."""

    return {
        sid: {
            "sharpe": 1.0,
            "max_drawdown": 0.05,
            "pnl": 1000.0,
        }
        for sid in strategy_ids
    }


def _post_apply(url: str, world_id: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Send the apply request and return the JSON response."""

    endpoint = f"{url.rstrip('/')}/worlds/{world_id}/apply"
    with httpx.Client(timeout=2.0) as client:
        response = client.post(endpoint, json=payload)
        response.raise_for_status()
        return response.json()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WorldService apply demo")
    parser.add_argument("--world-id", default="demo", help="Target world identifier")
    parser.add_argument(
        "--url",
        default="http://localhost:8080",
        help="Base URL for the WorldService HTTP API",
    )
    parser.add_argument(
        "--gating-policy",
        type=Path,
        default=_DEFAULT_POLICY_PATH,
        help="Path to the gating policy YAML document",
    )
    parser.add_argument(
        "--strategy",
        action="append",
        dest="strategies",
        default=["example_strategy"],
        help="Strategy IDs to include in the metrics payload",
    )
    parser.add_argument(
        "--run-id",
        help="Optional run identifier; generated when omitted",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the payload without posting to WorldService",
    )

    args = parser.parse_args(argv)

    strategies = list(dict.fromkeys(args.strategies))  # dedupe while preserving order
    run_id = args.run_id or f"demo-{uuid.uuid4().hex[:8]}"

    try:
        gating_policy = _load_gating_policy(args.gating_policy)
    except (OSError, ValueError) as exc:  # pragma: no cover - CLI I/O
        print(f"Failed to load gating policy: {exc}", file=sys.stderr)
        return 1

    payload = {
        "run_id": run_id,
        "metrics": _build_metrics(strategies),
        "gating_policy": gating_policy,
    }

    print("POST /worlds/%s/apply" % args.world_id)
    print(json.dumps(payload, indent=2, sort_keys=True))

    if args.dry_run:
        return 0

    try:
        body = _post_apply(args.url, args.world_id, payload)
    except httpx.HTTPError as exc:  # pragma: no cover - network errors
        print(f"Apply request failed: {exc}", file=sys.stderr)
        return 2

    print("Response:")
    print(json.dumps(body, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI execution
    raise SystemExit(main())
