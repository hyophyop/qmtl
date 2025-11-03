from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Request

from ..world_client import WorldServiceClient
from ..rebalancing_executor import (
    OrderOptions,
    orders_from_world_plan,
    orders_from_strategy_deltas,
)
from ..routes.dependencies import GatewayDependencyProvider
from qmtl.services.worldservice.schemas import MultiWorldRebalanceRequest
from qmtl.services.worldservice.rebalancing import allocate_strategy_deltas, PositionSlice


def create_router(deps: GatewayDependencyProvider) -> APIRouter:
    router = APIRouter()

    @router.post("/rebalancing/execute")
    async def post_rebalancing_execute(
        payload: MultiWorldRebalanceRequest,
        request: Request,
        world_client: WorldServiceClient = Depends(deps.provide_world_client),
    ) -> Dict[str, Any]:
        # 1) Fetch plan from WorldService
        plan_resp = await world_client.post_rebalance_plan(payload.model_dump(exclude_unset=True))

        # 2) Convert per-world plans into orders
        per_world_orders: Dict[str, List[dict]] = {}
        per_world_plans = plan_resp.get("per_world", {})
        for wid, p in per_world_plans.items():
            orders = orders_from_world_plan(
                # lightweight view into plan for executor
                type("_Plan", (), {
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
            )
            per_world_orders[wid] = orders

        # 3) Shared account global netting (optional)
        shared_account = request.query_params.get("shared_account", "false").lower() in {"1", "true", "yes"}
        orders_global: List[dict] | None = None
        if shared_account:
            global_deltas = plan_resp.get("global_deltas", [])
            orders_global = orders_from_symbol_deltas([
                type("_Delta", (), {
                    "symbol": d.get("symbol"),
                    "delta_qty": float(d.get("delta_qty", 0.0)),
                    "venue": d.get("venue"),
                })
                for d in global_deltas
            ])

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
                for od in orders_from_strategy_deltas(exec_deltas, options=OrderOptions()):
                    orders_per_strategy.append({"world_id": wid, "order": od})

        result: Dict[str, Any] = {"orders_per_world": per_world_orders}
        if orders_global is not None:
            result["orders_global"] = orders_global
        if orders_per_strategy is not None:
            result["orders_per_strategy"] = orders_per_strategy
        return result

    return router


__all__ = ["create_router"]
