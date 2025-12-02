from __future__ import annotations

import argparse
import sys
from typing import Callable, List

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
        choices=["list", "create", "info", "delete"],
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
    
    args = parser.parse_args(argv)
    if args.action in ("create", "info", "delete") and not args.name:
        print(_t("Error: World name required for {}").format(args.action), file=sys.stderr)
        return 1

    actions: dict[str, Callable[[], int]] = {
        "list": lambda: _world_list(),
        "create": lambda: _world_create(args),
        "info": lambda: _world_info(args),
        "delete": lambda: _world_delete(args),
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
