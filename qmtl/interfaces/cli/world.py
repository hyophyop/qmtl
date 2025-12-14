from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import sys
from pathlib import Path
import uuid
from typing import Any, Callable, Dict, List

from qmtl.utils.i18n import _ as _t

from .common import parse_preset_overrides
from .http_client import http_get, http_post, http_delete
from .http_client import http_request


def cmd_world(argv: List[str]) -> int:
    """World management commands.

    Typical Core Loop usage:
      1) Submit strategies with a world using `qmtl submit ... --world <id>`.
      2) Inspect world-level allocations and build/apply plans via:
         - `qmtl world allocations -w <id>`
         - `qmtl world apply <id> --run-id <id> [--plan-file plan.json]`
         - `qmtl world rebalance-plan ...` / `qmtl world rebalance-apply ...`
      3) Inspect evaluation runs / approval overrides:
         - `qmtl world run-status <world> --strategy <sid> [--run latest]`
         - `qmtl world live-approve <world> --strategy <sid> --run <run_id> --comment ...`
    """
    parser = argparse.ArgumentParser(
        prog="qmtl world",
        description=_t("World management commands"),
    )
    parser.add_argument(
        "action",
        choices=[
            "list",
            "create",
            "info",
            "delete",
            "status",
            "run-status",
            "campaign-tick",
            "live-approve",
            "live-reject",
            "live-apply",
            "live-candidates",
            "allocations",
            "apply",
            "rebalance-plan",
            "rebalance-apply",
        ],
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
        "--run-id",
        dest="run_id",
        default=None,
        help=_t("Run identifier for apply requests (default: auto-generate)"),
    )
    parser.add_argument(
        "--plan-file",
        dest="plan_file",
        default=None,
        help=_t("Path to a JSON apply plan (fields like activate/deactivate)"),
    )
    parser.add_argument(
        "--plan",
        dest="plan_inline",
        default=None,
        help=_t("Inline JSON string for apply plan (mutually exclusive with --plan-file)"),
    )
    parser.add_argument(
        "--activate",
        dest="plan_activate",
        default=None,
        help=_t("Comma-separated strategy ids to activate (shortcut to build plan.activate)"),
    )
    parser.add_argument(
        "--deactivate",
        dest="plan_deactivate",
        default=None,
        help=_t("Comma-separated strategy ids to deactivate (shortcut to build plan.deactivate)"),
    )
    parser.add_argument(
        "--gating-policy",
        dest="gating_policy",
        default=None,
        help=_t("Optional gating policy JSON for apply requests"),
    )
    parser.add_argument(
        "--strategy",
        dest="strategy_id",
        default=None,
        help=_t("Strategy identifier (for run-status/status/live-* actions)"),
    )
    parser.add_argument(
        "--run",
        dest="evaluation_run_id",
        default="latest",
        help=_t("Evaluation run id (or 'latest')"),
    )
    parser.add_argument(
        "--comment",
        dest="comment",
        default=None,
        help=_t("Approval comment/reason for live overrides"),
    )
    parser.add_argument(
        "--actor",
        dest="actor",
        default=None,
        help=_t("Actor identity for approvals (default: $QMTL_ACTOR or $USER)"),
    )
    parser.add_argument(
        "--plan-only",
        dest="plan_only",
        action="store_true",
        help=_t("Print computed plan and exit (no apply)"),
    )
    parser.add_argument(
        "--force",
        dest="force",
        action="store_true",
        help=_t("Force live-apply even if run is not approved"),
    )
    parser.add_argument(
        "--limit",
        dest="limit",
        type=int,
        default=20,
        help=_t("Limit candidate listing size (default: 20)"),
    )
    parser.add_argument(
        "--include-plan",
        dest="include_plan",
        action="store_true",
        help=_t("Include activate/deactivate plan in candidate listing"),
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
        "apply": lambda: _world_apply(args),
        "rebalance-plan": lambda: _rebalance(args, apply=False),
        "rebalance-apply": lambda: _rebalance(args, apply=True),
        "status": lambda: _world_status(args),
        "run-status": lambda: _world_run_status(args),
        "campaign-tick": lambda: _world_campaign_tick(args),
        "live-approve": lambda: _world_live_override(args, status="approved"),
        "live-reject": lambda: _world_live_override(args, status="rejected"),
        "live-apply": lambda: _world_live_apply(args),
        "live-candidates": lambda: _world_live_candidates(args),
    }
    return actions[args.action]()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(ts: str | None) -> datetime:
    if not ts:
        return datetime.min.replace(tzinfo=timezone.utc)
    candidate = str(ts).strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def _resolve_world_id(args: argparse.Namespace) -> str | None:
    world_id = getattr(args, "world_id", None) or getattr(args, "name", None)
    if not world_id:
        return None
    return str(world_id)


def _require_world_id(args: argparse.Namespace) -> str:
    world_id = _resolve_world_id(args)
    if not world_id:
        raise ValueError("world id required")
    return world_id


def _require_strategy_id(args: argparse.Namespace) -> str:
    strategy_id = args.strategy_id
    if not strategy_id:
        raise ValueError("strategy id required (--strategy)")
    return str(strategy_id)


def _resolve_actor(args: argparse.Namespace) -> str | None:
    actor = args.actor or os.environ.get("QMTL_ACTOR") or os.environ.get("USER")
    if actor is not None:
        actor = str(actor).strip() or None
    return actor


def _pick_latest_run_id(runs: object) -> str | None:
    if not isinstance(runs, list) or not runs:
        return None
    scored: list[tuple[datetime, datetime, str]] = []
    for item in runs:
        if not isinstance(item, dict):
            continue
        run_id = item.get("run_id")
        if not run_id:
            continue
        created_at = _parse_iso(item.get("created_at"))
        updated_at = _parse_iso(item.get("updated_at"))
        scored.append((updated_at, created_at, str(run_id)))
    if not scored:
        return None
    scored.sort(reverse=True)
    return scored[0][2]


def _world_run_status(args: argparse.Namespace) -> int:
    try:
        world_id = _require_world_id(args)
        strategy_id = _require_strategy_id(args)
    except ValueError as exc:
        print(_t("Error: {}").format(exc), file=sys.stderr)
        return 1

    run_id = str(args.evaluation_run_id or "latest")
    if run_id == "latest":
        status_code, runs = http_get(f"/worlds/{world_id}/strategies/{strategy_id}/runs")
        if status_code >= 400 or status_code == 0:
            err = runs.get("detail") if isinstance(runs, dict) else status_code
            print(_t("Error fetching evaluation runs: {}").format(err), file=sys.stderr)
            return 1
        resolved = _pick_latest_run_id(runs)
        if not resolved:
            print(_t("No evaluation runs found for strategy '{}'").format(strategy_id), file=sys.stderr)
            return 1
        run_id = resolved

    status_code, record = http_get(f"/worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}")
    if status_code == 404:
        print(_t("Evaluation run not found: {}").format(run_id), file=sys.stderr)
        return 1
    if status_code >= 400 or status_code == 0:
        err = record.get("detail") if isinstance(record, dict) else status_code
        print(_t("Error fetching evaluation run: {}").format(err), file=sys.stderr)
        return 1

    if isinstance(record, dict):
        summary = record.get("summary") if isinstance(record.get("summary"), dict) else {}
        validation = record.get("validation") if isinstance(record.get("validation"), dict) else {}
        print(_t("📌 Evaluation Run"))
        print("=" * 50)
        print(f"World:    {world_id}")
        print(f"Strategy: {strategy_id}")
        print(f"Run:      {record.get('run_id')}")
        print(f"Stage:    {record.get('stage')}")
        print(f"Risk:     {record.get('risk_tier')}")
        if summary:
            print(f"Status:   {summary.get('status')}")
            print(f"Reco:     {summary.get('recommended_stage')}")
            print(f"Override: {summary.get('override_status')}")
        if validation:
            print(f"Policy:   {validation.get('policy_version')}")
        return 0

    print(record)
    return 0


def _world_status(args: argparse.Namespace) -> int:
    try:
        world_id = _require_world_id(args)
    except ValueError as exc:
        print(_t("Error: {}").format(exc), file=sys.stderr)
        return 1

    status_code, decide = http_get(f"/worlds/{world_id}/decide")
    if status_code == 404:
        print(_t("World '{}' not found").format(world_id), file=sys.stderr)
        return 1
    if status_code >= 400 or status_code == 0:
        err = decide.get("detail") if isinstance(decide, dict) else status_code
        print(_t("Error fetching world decision: {}").format(err), file=sys.stderr)
        return 1

    status_code, desc = http_get(f"/worlds/{world_id}/describe")
    if status_code >= 400 or status_code == 0:
        desc = {}

    print(_t("🌍 World Status"))
    print("=" * 50)
    print(f"World:         {world_id}")
    if isinstance(desc, dict) and "allow_live" in desc:
        print(f"Allow live:    {bool(desc.get('allow_live'))}")
    if isinstance(decide, dict):
        print(f"Effective:     {decide.get('effective_mode')}")
        print(f"Reason:        {decide.get('reason')}")
        print(f"As of:         {decide.get('as_of')}")
        if decide.get("dataset_fingerprint"):
            print(f"Dataset FP:    {decide.get('dataset_fingerprint')}")

    if args.strategy_id:
        print()
        rc = _world_run_status(args)
        if rc != 0:
            return rc

        try:
            strategy_id = _require_strategy_id(args)
        except ValueError:
            return 0

        status_code, campaign_resp = http_get(
            f"/worlds/{world_id}/campaign/status",
            params={"strategy_id": strategy_id},
        )
        if status_code < 400 and status_code != 0 and isinstance(campaign_resp, dict):
            strategies = campaign_resp.get("strategies")
            if isinstance(strategies, list) and strategies:
                first = strategies[0] if isinstance(strategies[0], dict) else None
                if isinstance(first, dict):
                    print()
                    print(_t("🧭 Campaign Status"))
                    print("=" * 50)
                    print(f"Phase:         {first.get('phase')}")
                    print(f"Promote paper: {bool(first.get('promotable_to_paper'))}")
                    print(f"Promote live:  {bool(first.get('promotable_to_live'))}")
                    reasons = first.get("reasons")
                    if isinstance(reasons, list) and reasons:
                        rendered = ", ".join(str(v) for v in reasons if str(v).strip())
                        if rendered:
                            print(f"Reasons:       {rendered}")

        run_id = str(args.evaluation_run_id or "latest")
        if run_id == "latest":
            status_code, runs = http_get(f"/worlds/{world_id}/strategies/{strategy_id}/runs")
            if status_code >= 400 or status_code == 0:
                return 0
            resolved = _pick_latest_run_id(runs)
            if not resolved:
                return 0
            run_id = resolved

        status_code, plan_resp = http_get(
            f"/worlds/{world_id}/promotions/live/plan",
            params={"strategy_id": strategy_id, "run_id": run_id},
        )
        if status_code >= 400 or status_code == 0 or not isinstance(plan_resp, dict):
            return 0

        print()
        print(_t("🚦 Live Promotion"))
        print("=" * 50)
        print(f"Mode:          {plan_resp.get('promotion_mode')}")
        if plan_resp.get("eligible") is not None:
            print(f"Eligible:      {bool(plan_resp.get('eligible'))}")
        print(f"Pending:       {bool(plan_resp.get('pending_manual_approval'))}")
        blocked = plan_resp.get("blocked_reasons")
        if isinstance(blocked, list) and blocked:
            rendered = ", ".join(str(v) for v in blocked if str(v).strip())
            if rendered:
                print(f"Blocked:       {rendered}")
        if plan_resp.get("cooldown_remaining_sec") is not None:
            print(f"Cooldown sec:  {plan_resp.get('cooldown_remaining_sec')}")
        if plan_resp.get("max_live_slots") is not None:
            print(f"Max slots:     {plan_resp.get('max_live_slots')}")
        if plan_resp.get("canary_fraction") is not None:
            print(f"Canary:        {plan_resp.get('canary_fraction')}")
        return 0
    return 0


def _world_live_override(args: argparse.Namespace, *, status: str) -> int:
    try:
        world_id = _require_world_id(args)
        strategy_id = _require_strategy_id(args)
    except ValueError as exc:
        print(_t("Error: {}").format(exc), file=sys.stderr)
        return 1

    run_id = str(args.evaluation_run_id or "latest")
    if run_id == "latest":
        status_code, runs = http_get(f"/worlds/{world_id}/strategies/{strategy_id}/runs")
        if status_code >= 400 or status_code == 0:
            err = runs.get("detail") if isinstance(runs, dict) else status_code
            print(_t("Error fetching evaluation runs: {}").format(err), file=sys.stderr)
            return 1
        resolved = _pick_latest_run_id(runs)
        if not resolved:
            print(_t("No evaluation runs found for strategy '{}'").format(strategy_id), file=sys.stderr)
            return 1
        run_id = resolved

    payload: dict[str, Any] = {"status": status}
    if status == "approved":
        if not args.comment:
            print(_t("Error: --comment is required for approvals"), file=sys.stderr)
            return 1
        actor = _resolve_actor(args)
        if not actor:
            print(_t("Error: --actor required (or set $QMTL_ACTOR/$USER)"), file=sys.stderr)
            return 1
        payload.update(
            {
                "reason": str(args.comment),
                "actor": actor,
                "timestamp": _utc_now_iso(),
            }
        )
    else:
        if args.comment:
            payload["reason"] = str(args.comment)
        actor = _resolve_actor(args)
        if actor:
            payload["actor"] = actor
            payload["timestamp"] = _utc_now_iso()

    endpoint = (
        "/promotions/live/approve" if status == "approved" else "/promotions/live/reject"
    )
    status_code, record = http_post(
        f"/worlds/{world_id}{endpoint}",
        {"strategy_id": strategy_id, "run_id": run_id, **payload},
    )
    if status_code == 404:
        print(_t("Evaluation run not found: {}").format(run_id), file=sys.stderr)
        return 1
    if status_code >= 400 or status_code == 0:
        err = record.get("detail") if isinstance(record, dict) else status_code
        print(_t("Override update failed: {}").format(err), file=sys.stderr)
        return 1

    summary = record.get("summary") if isinstance(record, dict) else None
    if isinstance(summary, dict):
        print(_t("✅ Override recorded"))
        print(f"World:    {world_id}")
        print(f"Strategy: {strategy_id}")
        print(f"Run:      {run_id}")
        print(f"Override: {summary.get('override_status')}")
        return 0
    print(_t("Override recorded"))
    return 0


def _world_live_apply(args: argparse.Namespace) -> int:
    try:
        world_id = _require_world_id(args)
        strategy_id = _require_strategy_id(args)
    except ValueError as exc:
        print(_t("Error: {}").format(exc), file=sys.stderr)
        return 1

    run_id = str(args.evaluation_run_id or "latest")
    if run_id == "latest":
        status_code, runs = http_get(f"/worlds/{world_id}/strategies/{strategy_id}/runs")
        if status_code >= 400 or status_code == 0:
            err = runs.get("detail") if isinstance(runs, dict) else status_code
            print(_t("Error fetching evaluation runs: {}").format(err), file=sys.stderr)
            return 1
        resolved = _pick_latest_run_id(runs)
        if not resolved:
            print(_t("No evaluation runs found for strategy '{}'").format(strategy_id), file=sys.stderr)
            return 1
        run_id = resolved

    status_code, plan_resp = http_get(
        f"/worlds/{world_id}/promotions/live/plan",
        params={"strategy_id": strategy_id, "run_id": run_id},
    )
    if status_code >= 400 or status_code == 0 or not isinstance(plan_resp, dict):
        err = plan_resp.get("detail") if isinstance(plan_resp, dict) else status_code
        print(_t("Error fetching promotion plan: {}").format(err), file=sys.stderr)
        return 1

    plan = plan_resp.get("plan")
    if not isinstance(plan, dict) or not isinstance(plan.get("activate"), list) or not isinstance(plan.get("deactivate"), list):
        print(_t("Error: invalid promotion plan response"), file=sys.stderr)
        return 1

    if args.plan_only:
        print(
            json.dumps(
                {"world_id": world_id, "strategy_id": strategy_id, "run_id": run_id, "plan": plan},
                indent=2,
            )
        )
        return 0

    apply_run_id = args.run_id or str(uuid.uuid4())
    status_code, resp = http_post(
        f"/worlds/{world_id}/promotions/live/apply",
        {
            "strategy_id": strategy_id,
            "run_id": run_id,
            "apply_run_id": apply_run_id,
            "force": bool(args.force),
        },
    )
    if status_code >= 400 or status_code == 0:
        err = resp.get("detail") if isinstance(resp, dict) else status_code
        print(_t("Apply request failed: {}").format(err), file=sys.stderr)
        return 1

    print(_t("🚦 Apply request sent"))
    print(f"World:    {world_id}")
    print(f"Run ID:   {apply_run_id}")
    print(f"Plan:     activate={len(plan.get('activate') or [])}, deactivate={len(plan.get('deactivate') or [])}")
    phase = resp.get("phase") if isinstance(resp, dict) else None
    if phase:
        print(f"Phase:    {phase}")
    return 0


def _world_live_candidates(args: argparse.Namespace) -> int:
    try:
        world_id = _require_world_id(args)
    except ValueError as exc:
        print(_t("Error: {}").format(exc), file=sys.stderr)
        return 1

    limit = int(getattr(args, "limit", 20) or 20)
    include_plan = bool(getattr(args, "include_plan", False))
    status_code, payload = http_get(
        f"/worlds/{world_id}/promotions/live/candidates",
        params={"limit": limit, "include_plan": str(include_plan).lower()},
    )
    if status_code >= 400 or status_code == 0 or not isinstance(payload, dict):
        err = payload.get("detail") if isinstance(payload, dict) else status_code
        print(_t("Error fetching live promotion candidates: {}").format(err), file=sys.stderr)
        return 1

    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        print(_t("Error: invalid candidates response"), file=sys.stderr)
        return 1

    print(_t("🚦 Live Promotion Candidates"))
    print("=" * 60)
    print(f"World: {world_id}")
    print(f"Mode:  {payload.get('promotion_mode')}")
    print(f"Count: {len(candidates)}")
    if not candidates:
        return 0

    for item in candidates:
        if not isinstance(item, dict):
            continue
        sid = item.get("strategy_id")
        rid = item.get("run_id")
        status = item.get("status")
        pending = bool(item.get("pending_manual_approval"))
        eligible = bool(item.get("eligible"))
        blocked = item.get("blocked_reasons")
        blocked_text = ""
        if isinstance(blocked, list) and blocked:
            rendered = ", ".join(str(v) for v in blocked if str(v).strip())
            if rendered:
                blocked_text = rendered
        header = f"- {sid} run={rid} status={status} eligible={eligible} pending={pending}"
        print(header)
        if blocked_text:
            print(f"  blocked: {blocked_text}")
        plan = item.get("plan")
        if include_plan and isinstance(plan, dict):
            activate_list: list[Any] = []
            deactivate_list: list[Any] = []
            raw_activate = plan.get("activate")
            raw_deactivate = plan.get("deactivate")
            if isinstance(raw_activate, list):
                activate_list = list(raw_activate)
            if isinstance(raw_deactivate, list):
                deactivate_list = list(raw_deactivate)
            print(f"  plan: activate={len(activate_list)}, deactivate={len(deactivate_list)}")
    return 0


def _world_campaign_tick(args: argparse.Namespace) -> int:
    try:
        world_id = _require_world_id(args)
    except ValueError as exc:
        print(_t("Error: {}").format(exc), file=sys.stderr)
        return 1

    params: dict[str, object] = {}
    if args.strategy_id:
        params["strategy_id"] = str(args.strategy_id)

    status_code, payload = http_request(
        "post",
        f"/worlds/{world_id}/campaign/tick",
        params=params or None,
        payload={},
    )
    if status_code >= 400 or status_code == 0 or not isinstance(payload, dict):
        err = payload.get("detail") if isinstance(payload, dict) else status_code
        print(_t("Error fetching campaign tick: {}").format(err), file=sys.stderr)
        return 1

    actions = payload.get("actions")
    if not isinstance(actions, list):
        print(_t("Error: invalid campaign tick response"), file=sys.stderr)
        return 1

    print(_t("🧭 Campaign Tick"))
    print("=" * 60)
    print(f"World: {world_id}")
    print(f"Count: {len(actions)}")
    if not actions:
        return 0
    for item in actions:
        if not isinstance(item, dict):
            continue
        action = item.get("action")
        sid = item.get("strategy_id")
        stage = item.get("stage")
        reason = item.get("reason")
        method = item.get("suggested_method")
        endpoint = item.get("suggested_endpoint")
        line = f"- {action}"
        if sid:
            line += f" strategy={sid}"
        if stage:
            line += f" stage={stage}"
        if reason:
            line += f" reason={reason}"
        if method and endpoint:
            line += f" -> {method} {endpoint}"
        print(line)
    return 0


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
        required = {"world_id", "strategy_id", "symbol", "qty"}
        missing = sorted(required - set(entry))
        if missing:
            raise ValueError(f"Position entry {idx} missing fields: {', '.join(missing)}")
        mark = entry.get("mark")
        if mark is None:
            raise ValueError(
                "Position entry {} missing required field: mark".format(idx)
            )
        try:
            entry = dict(entry)
            entry["mark"] = float(mark)
        except (TypeError, ValueError):
            raise ValueError(f"Position entry {idx} has invalid mark: {entry.get('mark')}")
        positions.append(entry)
    return positions


def _fetch_current_allocations(world_id: str | None) -> Dict[str, float]:
    params: Dict[str, object] | None = {"world_id": world_id} if world_id else None
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
    params: Dict[str, object] | None = {"world_id": world_id} if world_id else None
    status_code, payload = http_get("/allocations", params)
    if status_code >= 400 or status_code == 0:
        err = payload.get("detail") if isinstance(payload, dict) else status_code
        print(_t("Error fetching allocations: {}").format(err), file=sys.stderr)
        _print_allocation_apply_hint(world_id)
        return 1
    allocations = payload.get("allocations") if isinstance(payload, dict) else None
    print(_t("🌍 World allocations"))
    print("=" * 40)
    if not allocations:
        print(_t("No allocation records found"))
        _print_allocation_apply_hint(world_id)
        return 0
    for wid, snapshot in sorted(allocations.items()):
        alloc = snapshot.get("allocation") if isinstance(snapshot, dict) else None
        strategy_total = None
        stale = False
        if isinstance(snapshot, dict):
            strat = snapshot.get("strategy_alloc_total")
            if isinstance(strat, dict):
                strategy_total = strat
            stale = bool(snapshot.get("stale"))
        alloc_display = f"{float(alloc):.4f}" if alloc is not None else "n/a"
        print(f"- {wid}: {alloc_display}")
        if stale:
            print(_t("  • Snapshot may be stale; refresh with `qmtl world allocations -w {}`").format(wid))
        if strategy_total:
            print("  strategies:")
            for sid, ratio in sorted(strategy_total.items()):
                print(f"    - {sid}: {float(ratio):.4f}")
    _print_allocation_apply_hint(world_id)
    return 0


def _world_apply(args: argparse.Namespace) -> int:
    world_id = args.world_id or args.name
    if not world_id:
        print(_t("Error: world id required for apply"), file=sys.stderr)
        return 1

    plan_payload: Dict[str, Any] | None = None
    if args.plan_inline and args.plan_file:
        print(_t("Error: use either --plan or --plan-file, not both"), file=sys.stderr)
        return 1
    if args.plan_inline:
        try:
            plan_payload = json.loads(args.plan_inline)
        except Exception as exc:
            print(_t("Error parsing inline plan JSON: {}").format(exc), file=sys.stderr)
            return 1
    if args.plan_file:
        try:
            file_payload = json.loads(Path(args.plan_file).read_text())
            if isinstance(file_payload, dict) and "plan" in file_payload:
                plan_payload = file_payload.get("plan")
            else:
                plan_payload = file_payload
        except Exception as exc:
            print(_t("Error reading plan file '{}': {}").format(args.plan_file, exc), file=sys.stderr)
            return 1

    if plan_payload and (args.plan_activate or args.plan_deactivate):
        print(_t("Error: --activate/--deactivate cannot be combined with --plan/--plan-file"), file=sys.stderr)
        return 1

    activate_list = _parse_plan_list(args.plan_activate) if args.plan_activate else []
    deactivate_list = _parse_plan_list(args.plan_deactivate) if args.plan_deactivate else []

    payload: Dict[str, Any] = {"run_id": args.run_id or str(uuid.uuid4())}
    if plan_payload is not None:
        payload["plan"] = plan_payload
    elif activate_list or deactivate_list:
        payload["plan"] = {"activate": activate_list, "deactivate": deactivate_list}

    if args.gating_policy:
        try:
            payload["gating_policy"] = json.loads(args.gating_policy)
        except Exception as exc:
            print(_t("Error parsing gating policy JSON: {}").format(exc), file=sys.stderr)
            return 1

    status_code, resp = http_post(f"/worlds/{world_id}/apply", payload)
    if status_code >= 400 or status_code == 0:
        err = resp.get("detail") if isinstance(resp, dict) else status_code
        print(_t("Apply request failed: {}").format(err), file=sys.stderr)
        return 1

    print(_t("🚦 Apply request sent"))
    print(f"World:  {world_id}")
    print(f"Run ID: {payload['run_id']}")
    phase = resp.get("phase") if isinstance(resp, dict) else None
    if phase:
        print(f"Phase:  {phase}")
    active = resp.get("active") if isinstance(resp, dict) else None
    if isinstance(active, list):
        print(_t("Active strategies:"))
        for sid in active:
            print(f"  - {sid}")
    if not payload.get("plan") and (args.plan_activate or args.plan_deactivate):
        print(_t("Plan: built from --activate/--deactivate flags"))
    _print_allocation_apply_hint(world_id)
    return 0


def _parse_plan_list(raw: str) -> list[str]:
    parts = [p.strip() for p in raw.split(",")] if raw else []
    return [p for p in parts if p]


def _print_allocation_apply_hint(world_id: str | None) -> None:
    wid = world_id or "<world>"
    alloc_cmd = f"qmtl world allocations -w {wid}"
    apply_cmd = f"qmtl world apply {wid} --run-id <id> [--plan-file plan.json]"
    print(_t("Hint: use `{alloc_cmd}` to refresh snapshots or `{apply_cmd}` to request apply/rollback.").format(
        alloc_cmd=alloc_cmd,
        apply_cmd=apply_cmd,
    ))


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
        if not current_alloc:
            print(
                _t(
                    "Error: no allocation snapshot available; provide --current or ensure the world has allocations"
                ),
                file=sys.stderr,
            )
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
