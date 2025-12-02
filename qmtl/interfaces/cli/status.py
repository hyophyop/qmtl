from __future__ import annotations

import argparse
import sys
from typing import List

from qmtl.utils.i18n import _ as _t
from .http_client import http_get, gateway_url


def cmd_status(argv: List[str]) -> int:
    """Check status of submitted strategies."""
    parser = argparse.ArgumentParser(
        prog="qmtl status",
        description=_t("Check status of submitted strategies"),
    )
    parser.add_argument("--strategy", "-s", default=None, help=_t("Strategy ID to inspect"))
    parser.add_argument("--world", "-w", default=None, help=_t("Filter by world (list mode)"))
    parser.add_argument("--status", default=None, help=_t("Filter by status (list mode)"))
    parser.add_argument("--limit", "-n", type=int, default=20, help=_t("Max items to list"))
    parser.add_argument("--json", action="store_true", help=_t("Output raw JSON"))
    parser.add_argument("--with-world-info", action="store_true", help=_t("Include world policy summary (single strategy)"))
    
    args = parser.parse_args(argv)
    if args.strategy:
        return _status_single(args)
    return _status_list(args)


def _status_single(args: argparse.Namespace) -> int:
    status_code, payload = http_get(f"/strategies/{args.strategy}/status")
    error = _extract_error(payload)
    if status_code == 404:
        print(_t("Strategy '{}' not found").format(args.strategy), file=sys.stderr)
        return 1
    if status_code >= 400 or status_code == 0:
        print(_t("Error fetching status: {}").format(error or status_code), file=sys.stderr)
        return 1

    if args.json:
        print(payload if payload is not None else "{}")
        return 0

    status_val, world, mode = _extract_status_fields(payload)
    _print_status_single(args.strategy, status_val, world, mode, args.with_world_info)
    return 0


def _status_list(args: argparse.Namespace) -> int:
    status_code, payload = http_get("/strategies", params=_status_query_params(args))
    err = _extract_error(payload)
    if status_code == 404:
        print(_t("Gateway does not support listing strategies (404)"), file=sys.stderr)
        return 1
    if status_code >= 400 or status_code == 0:
        print(_t("Error fetching strategies: {}").format(err or status_code), file=sys.stderr)
        return 1

    if args.json:
        print(payload if payload is not None else "[]")
        return 0

    _print_status_list(payload, args.limit)
    return 0


def _extract_error(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    return payload.get("detail") or payload.get("error")


def _extract_status_fields(payload: object) -> tuple[str | None, str | None, str | None]:
    if not isinstance(payload, dict):
        return None, None, None
    status_val = payload.get("status")
    world = payload.get("world") or payload.get("world_id")
    mode = payload.get("mode")
    return status_val, world, mode


def _print_status_single(strategy: str, status_val: str | None, world: str | None, mode: str | None, show_world: bool) -> None:
    print(_t("📊 Strategy Status"))
    print("=" * 40)
    print(f"Strategy: {strategy}")
    print(f"Status:   {status_val or 'unknown'}")
    if world:
        print(f"World:    {world}")
    if mode:
        print(f"Mode:     {mode}")
    if show_world and world:
        _print_world_policy(world)
    print()
    print(_t("Gateway: {}").format(gateway_url()))


def _print_status_list(payload: object, limit: int) -> None:
    strategies = payload if isinstance(payload, list) else []
    print(_t("📊 Strategy Status List"))
    print("=" * 60)
    if not strategies:
        print(_t("No strategies found"))
        return
    for item in strategies[: limit]:
        print(_format_strategy_row(item))


def _print_world_policy(world: str) -> None:
    ws_code, ws_payload = http_get(f"/worlds/{world}/describe")
    if ws_code == 200 and isinstance(ws_payload, dict):
        human = ws_payload.get("policy_human") or "n/a"
        preset = ws_payload.get("policy_preset") or "n/a"
        version = ws_payload.get("default_policy_version") or "n/a"
        print(f"Policy:   preset={preset}, version={version}, {human}")


def _status_query_params(args: argparse.Namespace) -> dict[str, object] | None:
    params: dict[str, object] = {}
    if args.world:
        params["world"] = args.world
    if args.status:
        params["status"] = args.status
    if args.limit:
        params["limit"] = args.limit
    return params or None


def _format_strategy_row(item: object) -> str:
    if not isinstance(item, dict):
        return str(item)
    sid = item.get("id") or item.get("strategy_id") or "<unknown>"
    status_val = item.get("status") or item.get("state") or "unknown"
    world = item.get("world") or item.get("world_id") or "-"
    mode = item.get("mode") or "-"
    return f"- {sid} | status={status_val} | world={world} | mode={mode}"
