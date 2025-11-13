from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
import logging
import uuid
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from fastapi import APIRouter, Depends, HTTPException, Request, status


if hasattr(status, "HTTP_422_UNPROCESSABLE_CONTENT"):
    HTTP_422_UNPROCESSABLE = status.HTTP_422_UNPROCESSABLE_CONTENT
else:
    HTTP_422_UNPROCESSABLE = status.HTTP_422_UNPROCESSABLE_ENTITY

from .. import metrics as gw_metrics
from ..database import Database
from ..rebalancing_executor import (
    OrderOptions,
    VenuePolicy,
    orders_from_world_plan,
    orders_from_strategy_deltas,
    orders_from_symbol_deltas,
)
from ..routes.dependencies import GatewayDependencyProvider
from ..shared_account_policy import SharedAccountPolicy
from ..strategy_manager import StrategyManager
from ..world_client import WorldServiceClient
from qmtl.services.worldservice.rebalancing import allocate_strategy_deltas, PositionSlice
from qmtl.services.worldservice.schemas import MultiWorldRebalanceRequest

logger = logging.getLogger(__name__)


def create_router(deps: GatewayDependencyProvider) -> APIRouter:
    router = APIRouter()

    @router.post("/rebalancing/execute")
    async def post_rebalancing_execute(
        payload: MultiWorldRebalanceRequest,
        request: Request,
        world_client: WorldServiceClient = Depends(deps.provide_world_client),
        manager: StrategyManager = Depends(deps.provide_manager),
        database: Database = Depends(deps.provide_database),
        enforce_live_guard: bool = Depends(deps.provide_enforce_live_guard),
        rebalance_schema_version: int = Depends(deps.provide_rebalance_schema_version),
        alpha_metrics_capable: bool = Depends(deps.provide_alpha_metrics_capable),
    ) -> Dict[str, Any]:
        submit_requested = _parse_bool(request.query_params.get("submit"))

        if submit_requested and enforce_live_guard:
            if request.headers.get("X-Allow-Live") != "true":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": "E_PERMISSION_DENIED",
                        "message": "live trading not allowed",
                    },
                )

        # 1) Fetch plan from WorldService
        preferred_schema_version = max(1, rebalance_schema_version or 1)
        fallback_schema_version = 1 if preferred_schema_version > 1 else None
        plan_resp = await world_client.post_rebalance_plan(
            payload.model_dump(exclude_unset=True),
            schema_version=preferred_schema_version,
            fallback_schema_version=fallback_schema_version,
        )

        negotiated_schema_version_raw = None
        if isinstance(plan_resp, Mapping):
            negotiated_schema_version_raw = plan_resp.get("schema_version")
        if isinstance(negotiated_schema_version_raw, int):
            negotiated_schema_version = max(1, negotiated_schema_version_raw)
        elif fallback_schema_version is not None and fallback_schema_version < preferred_schema_version:
            negotiated_schema_version = max(1, fallback_schema_version)
        else:
            negotiated_schema_version = preferred_schema_version

        # 2) Convert per-world plans into orders
        per_world_orders: Dict[str, List[dict]] = {}
        per_world_plans = plan_resp.get("per_world", {})
        venue_policies = _resolve_venue_policies(request)
        lot_sizes = payload.lot_size_by_symbol or {}
        marks_by_world, marks_global = _collect_mark_snapshots(payload.positions or [])
        current_net_notional = _aggregate_net_notional(payload.positions or [])
        min_trade_notional = payload.min_trade_notional
        for wid, p in per_world_plans.items():
            plan_obj = type(
                "_Plan",
                (),
                {
                    "world_id": wid,
                    "scale_world": p.get("scale_world", 1.0),
                    "scale_by_strategy": p.get("scale_by_strategy", {}),
                    "deltas": [
                        type(
                            "_Delta",
                            (),
                            {
                                "symbol": d.get("symbol"),
                                "delta_qty": float(d.get("delta_qty", 0.0)),
                                "venue": d.get("venue"),
                            },
                        )
                        for d in p.get("deltas", [])
                    ],
                },
            )
            orders = orders_from_world_plan(
                plan_obj,
                options=OrderOptions(
                    lot_size_by_symbol=lot_sizes,
                    min_trade_notional=min_trade_notional,
                    marks_by_symbol=marks_by_world.get(wid, {}),
                    venue_policies=venue_policies,
                ),
            )
            per_world_orders[wid] = orders

        # 3) Shared account global netting (optional) or overlay mode
        shared_account = request.query_params.get("shared_account", "false").lower() in {"1", "true", "yes"}
        mode = (payload.mode or 'scaling').lower() if hasattr(payload, 'mode') else 'scaling'
        orders_global: List[dict] | None = None
        policy: SharedAccountPolicy | None = getattr(
            request.app.state, "shared_account_policy", None
        )
        if shared_account:
            if policy is None or not policy.enabled:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": "E_SHARED_ACCOUNT_DISABLED",
                        "message": "shared-account execution is disabled",
                    },
                )
            global_deltas = plan_resp.get("global_deltas", [])
            orders_global = orders_from_symbol_deltas([
                type("_Delta", (), {
                    "symbol": d.get("symbol"),
                    "delta_qty": float(d.get("delta_qty", 0.0)),
                    "venue": d.get("venue"),
                })
                for d in global_deltas
            ], options=OrderOptions(
                lot_size_by_symbol=lot_sizes,
                min_trade_notional=min_trade_notional,
                marks_by_symbol=marks_global,
                venue_policies=venue_policies,
            ))
            evaluation = policy.evaluate(
                orders_global,
                marks_by_symbol=marks_global,
                total_equity=payload.total_equity,
                current_net_notional=current_net_notional,
            )
            if not evaluation.allowed:
                message = evaluation.reason or "shared-account policy rejected execution"
                raise HTTPException(
                    status_code=HTTP_422_UNPROCESSABLE,
                    detail={
                        "code": "E_SHARED_ACCOUNT_POLICY",
                        "message": message,
                        "context": dict(evaluation.context),
                    },
                )
        elif mode in ('overlay', 'hybrid'):
            raise NotImplementedError("Overlay mode is not implemented yet. Use mode='scaling'.")

        # 4) Optionally split into per-strategy orders when requested (query param)
        per_strategy = request.query_params.get("per_strategy", "false").lower() in {"1", "true", "yes"}
        orders_per_strategy: List[Dict[str, Any]] | None = None
        if per_strategy and not shared_account:
            # Build PositionSlice list from request payload for allocation
            positions = [
                PositionSlice(
                    world_id=pos.world_id,
                    strategy_id=pos.strategy_id,
                    symbol=pos.symbol,
                    qty=pos.qty,
                    mark=pos.mark,
                    venue=pos.venue,
                )
                for pos in payload.positions
            ]

            strategy_after_total = payload.strategy_alloc_after_total or {}
            orders_per_strategy = []
            for wid, p in per_world_plans.items():
                # Reconstruct plan object for allocate_strategy_deltas
                plan_obj = type("_Plan", (), {
                    "world_id": wid,
                    "scale_world": p.get("scale_world", 1.0),
                    "scale_by_strategy": p.get("scale_by_strategy", {}),
                    "deltas": [
                        type("_Delta", (), {
                            "symbol": d.get("symbol"),
                            "delta_qty": float(d.get("delta_qty", 0.0)),
                            "venue": d.get("venue"),
                        })
                        for d in p.get("deltas", [])
                    ],
                })

                fallback = strategy_after_total.get(wid)
                exec_deltas = allocate_strategy_deltas(wid, plan_obj, positions, fallback_weights=fallback)
                # Convert to orders
                strategy_orders = orders_from_strategy_deltas(
                    exec_deltas,
                    options=OrderOptions(
                        lot_size_by_symbol=lot_sizes,
                        min_trade_notional=min_trade_notional,
                        marks_by_symbol=marks_by_world.get(wid, {}),
                        venue_policies=venue_policies,
                    ),
                )
                for delta, od in zip(exec_deltas, strategy_orders):
                    orders_per_strategy.append(
                        {"world_id": wid, "strategy_id": delta.strategy_id, "order": od}
                    )

        result: Dict[str, Any] = {"orders_per_world": per_world_orders}
        if orders_global is not None:
            result["orders_global"] = orders_global
        if orders_per_strategy is not None:
            result["orders_per_strategy"] = orders_per_strategy

        if submit_requested:
            submitted = await _submit_rebalance_orders(
                manager,
                database,
                world_client,
                per_world_orders,
                orders_global,
                orders_per_strategy,
                shared_account=shared_account,
            )
            result["submitted"] = submitted
        else:
            result["submitted"] = False
        alpha_metrics_available = bool(plan_resp.get("alpha_metrics"))
        result["rebalance_schema_version"] = negotiated_schema_version
        result["alpha_metrics_capable"] = bool(
            alpha_metrics_capable
            and negotiated_schema_version >= 2
            and alpha_metrics_available
        )
        return result

    return router


__all__ = ["create_router"]


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _collect_mark_snapshots(
    positions: Sequence[PositionSlice],
) -> tuple[dict[str, Mapping[tuple[str | None, str], float]], Mapping[tuple[str | None, str], float]]:
    world_marks: dict[str, dict[tuple[str | None, str], List[float]]] = defaultdict(lambda: defaultdict(list))
    aggregate: dict[tuple[str | None, str], List[float]] = defaultdict(list)
    for pos in positions:
        mark = float(getattr(pos, "mark", 0.0) or 0.0)
        if mark <= 0:
            continue
        key_specific = (pos.venue, pos.symbol)
        key_symbol = (None, pos.symbol)
        world_marks[pos.world_id][key_specific].append(mark)
        world_marks[pos.world_id][key_symbol].append(mark)
        aggregate[key_specific].append(mark)
        aggregate[key_symbol].append(mark)

    def _finalize(source: Mapping[tuple[str | None, str], List[float]]) -> Mapping[tuple[str | None, str], float]:
        return {key: sum(values) / len(values) for key, values in source.items() if values}

    finalized_world = {wid: _finalize(bucket) for wid, bucket in world_marks.items()}
    finalized_global = _finalize(aggregate)
    return finalized_world, finalized_global


def _aggregate_net_notional(positions: Sequence[PositionSlice]) -> float:
    net = 0.0
    for pos in positions:
        qty = float(getattr(pos, "qty", 0.0) or 0.0)
        mark = float(getattr(pos, "mark", 0.0) or 0.0)
        net += qty * mark
    return net


def _resolve_venue_policies(request: Request) -> Mapping[str, VenuePolicy]:
    raw = getattr(request.app.state, "rebalance_venue_policies", None)
    if not raw:
        return {}
    policies: dict[str, VenuePolicy] = {}
    for venue, value in dict(raw).items():
        if isinstance(value, VenuePolicy):
            policies[venue] = value
            continue
        if isinstance(value, Mapping):
            policies[venue] = VenuePolicy(
                supports_reduce_only=bool(value.get("supports_reduce_only", True)),
                reduce_only_requires_ioc=bool(value.get("reduce_only_requires_ioc", False)),
                default_time_in_force=value.get("default_time_in_force"),
            )
    return policies


async def _submit_rebalance_orders(
    manager: StrategyManager,
    database: Database,
    world_client: WorldServiceClient,
    per_world_orders: Mapping[str, Sequence[Mapping[str, Any]]],
    orders_global: Sequence[Mapping[str, Any]] | None,
    orders_per_strategy: Sequence[Mapping[str, Any]] | None,
    *,
    shared_account: bool,
) -> bool:
    writer = manager.commit_log_writer
    if writer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "E_COMMITLOG_DISABLED",
                "message": "commit log unavailable",
            },
        )

    world_ids = set(per_world_orders.keys())
    if orders_per_strategy:
        world_ids.update(item.get("world_id") for item in orders_per_strategy)
    world_modes = await _resolve_world_modes(world_client, {wid for wid in world_ids if wid})

    submitted_any = False
    # Submit per-world batches
    for wid, orders in per_world_orders.items():
        submitted_any |= await _publish_batch(
            writer,
            database,
            wid,
            "per_world",
            list(orders),
            world_modes.get(wid),
            shared_account=shared_account,
        )

    if orders_global:
        submitted_any |= await _publish_batch(
            writer,
            database,
            "global",
            "global",
            list(orders_global),
            None,
            shared_account=True,
        )

    if orders_per_strategy:
        per_world_entries: dict[str, List[dict[str, Any]]] = defaultdict(list)
        for item in orders_per_strategy:
            wid = item["world_id"]
            per_world_entries[wid].append(item)
        for wid, entries in per_world_entries.items():
            orders_only = [entry["order"] for entry in entries]
            submitted_any |= await _publish_batch(
                writer,
                database,
                wid,
                "per_strategy",
                orders_only,
                world_modes.get(wid),
                shared_account=False,
                extra_orders_payload=entries,
            )

    return submitted_any


async def _publish_batch(
    writer,
    database: Database,
    world_id: str,
    scope: str,
    orders: Sequence[Mapping[str, Any]],
    mode: str | None,
    *,
    shared_account: bool,
    extra_orders_payload: Sequence[Mapping[str, Any]] | None = None,
) -> bool:
    if not orders:
        return False
    total, reduce_only_count, ratio = _summarize_orders(orders)
    gw_metrics.record_rebalance_submission(world_id, scope, orders)

    payload_orders: Sequence[Mapping[str, Any]] = (
        extra_orders_payload if extra_orders_payload is not None else orders
    )
    submitted_at = datetime.now(timezone.utc).isoformat()
    event_payload: dict[str, Any] = {
        "event": "gateway.rebalance",
        "version": 1,
        "world_id": world_id,
        "scope": scope,
        "orders": list(payload_orders),
        "counts": {"total": total, "reduce_only": reduce_only_count},
        "reduce_only_ratio": ratio,
        "submitted_at": submitted_at,
    }
    if mode:
        event_payload["mode"] = mode
    if shared_account:
        event_payload["shared_account"] = True

    batch_id = f"{world_id}:{uuid.uuid4().hex}"
    try:
        await writer.publish_rebalance_batch(batch_id, event_payload)
    except Exception as exc:  # pragma: no cover - defensive log path
        logger.exception("Failed to publish rebalancing batch", extra={"world_id": world_id, "scope": scope})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "E_COMMITLOG",
                "message": "commit log unavailable",
            },
        ) from exc

    await _record_rebalance_audit(
        database,
        world_id,
        scope,
        total,
        ratio,
        submitted_at,
        mode,
        shared_account,
    )
    return True


async def _record_rebalance_audit(
    database: Database,
    world_id: str,
    scope: str,
    total: int,
    ratio: float,
    submitted_at: str,
    mode: str | None,
    shared_account: bool,
) -> None:
    if database is None:
        return
    event = {
        "scope": scope,
        "world_id": world_id,
        "order_count": total,
        "reduce_only_ratio": ratio,
        "shared_account": shared_account,
        "submitted_at": submitted_at,
    }
    if mode:
        event["mode"] = mode
    try:
        await database.append_event(
            f"rebalance:{world_id}", f"REB_SUBMIT:{json.dumps(event, sort_keys=True)}"
        )
    except Exception:  # pragma: no cover - audit best effort
        logger.exception(
            "Failed to append rebalancing audit event",
            extra={"world_id": world_id, "scope": scope},
        )


async def _resolve_world_modes(
    world_client: WorldServiceClient,
    world_ids: Iterable[str | None],
) -> dict[str, str]:
    modes: dict[str, str] = {}
    for wid in world_ids:
        if not wid:
            continue
        try:
            data = await world_client.get_world(wid)
        except Exception:
            continue
        mode = None
        if isinstance(data, Mapping):
            if isinstance(data.get("world"), Mapping):
                mode = data["world"].get("mode")
            if mode is None:
                mode = data.get("mode") or data.get("effective_mode")
        if isinstance(mode, str):
            modes[wid] = mode
    return modes


def _summarize_orders(orders: Sequence[Mapping[str, Any]]) -> tuple[int, int, float]:
    total = len(orders)
    reduce_only = sum(1 for order in orders if order.get("reduce_only"))
    ratio = float(reduce_only) / float(total) if total else 0.0
    return total, reduce_only, ratio
