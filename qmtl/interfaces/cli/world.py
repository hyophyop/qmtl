from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List

from qmtl.utils.i18n import _ as _t

from .common import parse_preset_overrides
from .http_client import http_get, http_post, http_delete


def cmd_world(argv: List[str]) -> int:
    """World management commands."""
    parser = argparse.ArgumentParser(
        prog="qmtl world",
        description=_t("World management commands"),
    )
    parser.add_argument(
        "action",
        choices=["list", "create", "info", "delete", "allocations", "rebalance-plan", "rebalance-apply"],
        help=_t("Action to perform"),
    )
    parser.add_argument(
        "name",
        nargs="?",
        help=_t("World name (for create/info/delete)"),
    )
    parser.add_argument(
        "--policy", "-p",
        choices=["sandbox", "conservative", "moderate", "aggressive"],
        default="conservative",
        help=_t("Policy preset for new world (default: conservative)"),
    )
    parser.add_argument(
        "--preset-mode",
        choices=["shared", "clone", "extend"],
        default=None,
        help=_t("How to apply preset policy to the world (metadata only)"),
    )
    parser.add_argument(
        "--preset-version",
        default=None,
        help=_t("Optional preset version identifier for the world"),
    )
    parser.add_argument(
        "--preset-override",
        action="append",
        default=[],
        help=_t("Override preset thresholds (key=value, e.g., max_drawdown.max=0.15)"),
    )
    parser.add_argument(
        "--world-id", "-w",
        dest="world_id",
        default=None,
        help=_t("World identifier for allocation lookups"),
    )
    parser.add_argument(
        "--target", "-t",
        dest="target_allocations",
        default=None,
        help=_t("Target world allocations for rebalance commands (e.g., w1=0.6,w2=0.4)"),
    )
    parser.add_argument(
        "--current",
        dest="current_allocations",
        default=None,
        help=_t("Override current allocations instead of fetching from the service"),
    )
    parser.add_argument(
        "--positions-file",
        dest="positions_file",
        default=None,
        help=_t("Path to a JSON file containing position slices for rebalancing"),
    )
    parser.add_argument(
        "--total-equity",
        dest="total_equity",
        type=float,
        default=1.0,
        help=_t("Total equity used to scale allocations (default: 1.0)"),
    )
    parser.add_argument(
        "--schema-version",
        dest="schema_version",
        type=int,
        default=None,
        help=_t("Optional schema version for rebalance payloads"),
    )
    parser.add_argument(
        "--mode",
        dest="mode",
        choices=["scaling"],
        default=None,
        help=_t("Rebalance mode (default: scaling)"),
    )

    args = parser.parse_args(argv)
    if args.action in ("create", "info", "delete") and not args.name:
        print(_t("Error: World name required for {}").format(args.action), file=sys.stderr)
        return 1

    actions: dict[str, Callable[[], int]] = {
        "list": lambda: _world_list(),
        "create": lambda: _world_create(args),
        "info": lambda: _world_info(args),
        "delete": lambda: _world_delete(args),
        "allocations": lambda: _world_allocations(args),
        "rebalance-plan": lambda: _rebalance(args, apply=False),
        "rebalance-apply": lambda: _rebalance(args, apply=True),
    }
    return actions[args.action]()


def _world_list() -> int:
    status_code, payload = http_get("/worlds")
    if status_code >= 400 or status_code == 0:
        err = payload.get("error") if isinstance(payload, dict) else status_code
        print(_t("Error fetching worlds: {}").format(err), file=sys.stderr)
        return 1
    worlds = payload if isinstance(payload, list) else []
    print(_t("🌍 Available Worlds"))
    print("=" * 40)
    if not worlds:
        print(_t("No worlds found"))
        return 0
    for w in worlds:
        wid = w.get("id") if isinstance(w, dict) else str(w)
        name = w.get("name") if isinstance(w, dict) else ""
        if name:
            print(f"- {wid} ({name})")
        else:
            print(f"- {wid}")
    return 0


def _world_create(args: argparse.Namespace) -> int:
    overrides = parse_preset_overrides(args.preset_override or [])
    payload = {"id": args.name, "name": args.name}
    status_code, resp = http_post("/worlds", payload)
    if status_code >= 400 or status_code == 0:
        err = resp.get("detail") if isinstance(resp, dict) else status_code
        print(_t("Error creating world: {}").format(err), file=sys.stderr)
        return 1

    status_code, policy_resp = http_post(
        f"/worlds/{args.name}/policies",
        {
            "preset": args.policy,
            "preset_mode": args.preset_mode,
            "preset_version": args.preset_version,
            "preset_overrides": overrides or None,
        },
    )
    if status_code >= 400 or status_code == 0:
        err = policy_resp.get("detail") if isinstance(policy_resp, dict) else status_code
        print(_t("World created, but failed to apply policy: {}").format(err), file=sys.stderr)
        return 1
    print(_t("World '{}' created with policy preset '{}'").format(args.name, args.policy))
    return 0


def _world_info(args: argparse.Namespace) -> int:
    status_code, resp = http_get(f"/worlds/{args.name}/describe")
    if status_code == 404:
        print(_t("World '{}' not found").format(args.name), file=sys.stderr)
        return 1
    if status_code >= 400 or status_code == 0:
        err = resp.get("detail") if isinstance(resp, dict) else status_code
        print(_t("Error fetching world info: {}").format(err), file=sys.stderr)
        return 1
    print(_t("🌍 World Info"))
    print("=" * 40)
    if isinstance(resp, dict):
        print(f"id: {resp.get('id')}")
        print(f"name: {resp.get('name')}")
        print(f"default_policy_version: {resp.get('default_policy_version')}")
        print(f"policy_preset: {resp.get('policy_preset') or 'n/a'}")
        print(f"policy_human: {resp.get('policy_human') or 'n/a'}")
    else:
        print(resp)
    return 0


def _world_delete(args: argparse.Namespace) -> int:
    status_code, resp = http_delete(f"/worlds/{args.name}")
    if status_code == 404:
        print(_t("World '{}' not found").format(args.name), file=sys.stderr)
        return 1
    if status_code >= 400 or status_code == 0:
        err = resp.get("detail") if isinstance(resp, dict) else status_code
        print(_t("Error deleting world: {}").format(err), file=sys.stderr)
        return 1
    print(_t("World '{}' deleted").format(args.name))
    return 0


def _parse_ratio_mapping(raw: str) -> Dict[str, float]:
    pairs = [p.strip() for p in raw.split(",") if p.strip()]
    if not pairs:
        raise ValueError("allocation string cannot be empty")
    mapping: Dict[str, float] = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"Invalid entry '{pair}', expected key=value")
        key, value = pair.split("=", 1)
        if not key.strip():
            raise ValueError("Allocation key cannot be empty")
        mapping[key.strip()] = float(value)
    return mapping


def _load_positions(path: str | None) -> List[Dict[str, Any]]:
    if not path:
        return []
    data = json.loads(Path(path).read_text())
    if not isinstance(data, list):
        raise ValueError("positions file must contain a list")
    positions: List[Dict[str, Any]] = []
    for idx, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValueError(f"Position entry {idx} must be an object")
        required = {"world_id", "strategy_id", "symbol", "qty", "mark"}
        missing = sorted(required - set(entry))
        if missing:
            raise ValueError(f"Position entry {idx} missing fields: {', '.join(missing)}")
        try:
            entry = dict(entry)
            entry["mark"] = float(entry["mark"])
        except (TypeError, ValueError):
            raise ValueError(f"Position entry {idx} has invalid mark: {entry.get('mark')}")
        positions.append(entry)
    return positions


def _fetch_current_allocations(world_id: str | None) -> Dict[str, float]:
    params = {"world_id": world_id} if world_id else None
    status_code, payload = http_get("/allocations", params)
    if status_code >= 400 or status_code == 0:
        err = payload.get("detail") if isinstance(payload, dict) else status_code
        raise RuntimeError(_t("Error fetching allocations: {}").format(err))
    allocations_block = payload.get("allocations") if isinstance(payload, dict) else None
    if not isinstance(allocations_block, dict):
        return {}
    allocations: Dict[str, float] = {}
    for wid, snapshot in allocations_block.items():
        if isinstance(snapshot, dict) and "allocation" in snapshot:
            try:
                allocations[wid] = float(snapshot.get("allocation", 0.0))
            except (TypeError, ValueError):
                continue
    return allocations


def _world_allocations(args: argparse.Namespace) -> int:
    world_id = args.world_id or args.name
    params = {"world_id": world_id} if world_id else None
    status_code, payload = http_get("/allocations", params)
    if status_code >= 400 or status_code == 0:
        err = payload.get("detail") if isinstance(payload, dict) else status_code
        print(_t("Error fetching allocations: {}").format(err), file=sys.stderr)
        return 1
    allocations = payload.get("allocations") if isinstance(payload, dict) else None
    print(_t("🌍 World allocations"))
    print("=" * 40)
    if not allocations:
        print(_t("No allocation records found"))
        return 0
    for wid, snapshot in sorted(allocations.items()):
        alloc = snapshot.get("allocation") if isinstance(snapshot, dict) else None
        strategy_total = None
        if isinstance(snapshot, dict):
            strat = snapshot.get("strategy_alloc_total")
            if isinstance(strat, dict):
                strategy_total = strat
        alloc_display = f"{float(alloc):.4f}" if alloc is not None else "n/a"
        print(f"- {wid}: {alloc_display}")
        if strategy_total:
            print("  strategies:")
            for sid, ratio in sorted(strategy_total.items()):
                print(f"    - {sid}: {float(ratio):.4f}")
    return 0


def _render_rebalance_response(payload: Any) -> None:
    print(_t("🧮 Rebalance plan"))
    print("=" * 40)
    if not isinstance(payload, dict):
        print(payload)
        return
    per_world = payload.get("per_world") if isinstance(payload, dict) else None
    if per_world:
        print(_t("Per-world adjustments:"))
        for wid, plan in sorted(per_world.items()):
            scale_world = plan.get("scale_world") if isinstance(plan, dict) else None
            print(f"- {wid}: scale={scale_world}")
            deltas = plan.get("deltas") if isinstance(plan, dict) else None
            if deltas:
                for delta in deltas:
                    if not isinstance(delta, dict):
                        continue
                    symbol = delta.get("symbol")
                    qty = delta.get("delta_qty")
                    venue = delta.get("venue")
                    venue_part = f" @ {venue}" if venue else ""
                    print(f"    • {symbol}: {qty}{venue_part}")
    global_deltas = payload.get("global_deltas") if isinstance(payload, dict) else None
    if global_deltas:
        print(_t("Global deltas:"))
        for delta in global_deltas:
            if not isinstance(delta, dict):
                continue
            symbol = delta.get("symbol")
            qty = delta.get("delta_qty")
            venue = delta.get("venue")
            venue_part = f" @ {venue}" if venue else ""
            print(f"- {symbol}: {qty}{venue_part}")


def _rebalance(args: argparse.Namespace, *, apply: bool) -> int:
    if not args.target_allocations:
        print(_t("Error: --target is required for rebalance commands"), file=sys.stderr)
        return 1
    try:
        target_alloc = _parse_ratio_mapping(args.target_allocations)
    except ValueError as exc:
        print(_t("Invalid target allocations: {}").format(exc), file=sys.stderr)
        return 1

    try:
        positions = _load_positions(args.positions_file)
    except ValueError as exc:
        print(_t("Invalid positions: {}").format(exc), file=sys.stderr)
        return 1

    if args.current_allocations:
        try:
            current_alloc = _parse_ratio_mapping(args.current_allocations)
        except ValueError as exc:
            print(_t("Invalid current allocations: {}").format(exc), file=sys.stderr)
            return 1
    else:
        try:
            current_alloc = _fetch_current_allocations(args.world_id)
        except RuntimeError as exc:
            print(exc, file=sys.stderr)
            return 1

    payload: Dict[str, Any] = {
        "total_equity": args.total_equity,
        "world_alloc_before": current_alloc or {wid: 0.0 for wid in target_alloc},
        "world_alloc_after": target_alloc,
        "positions": positions,
    }
    if args.schema_version:
        payload["schema_version"] = args.schema_version
    if args.mode:
        payload["mode"] = args.mode

    endpoint = "/rebalancing/apply" if apply else "/rebalancing/plan"
    status_code, resp = http_post(endpoint, payload)
    if status_code >= 400 or status_code == 0:
        err = resp.get("detail") if isinstance(resp, dict) else status_code
        print(_t("Rebalance request failed: {}").format(err), file=sys.stderr)
        return 1
    _render_rebalance_response(resp)
    return 0
