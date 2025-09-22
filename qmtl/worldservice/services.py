from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Sequence

from fastapi import HTTPException

from qmtl.common.hashutils import hash_bytes
from qmtl.transforms.linearity_metrics import (
    equity_linearity_metrics,
    equity_linearity_metrics_v2,
)

from .controlbus_producer import ControlBusProducer
from .policy import GatingPolicy
from .policy_engine import evaluate_policy
from .schemas import (
    ActivationEnvelope,
    ActivationRequest,
    ApplyAck,
    ApplyRequest,
    ApplyResponse,
    EvaluateRequest,
    StrategySeries,
)
from .storage import EXECUTION_DOMAINS, Storage


class WorldService:
    """Business logic helpers for the world service FastAPI application."""

    def __init__(self, store: Storage, bus: ControlBusProducer | None = None) -> None:
        self.store = store
        self.bus = bus
        self.apply_locks: Dict[str, asyncio.Lock] = {}
        self.apply_runs: Dict[str, Dict[str, Any]] = {}

    async def evaluate(self, world_id: str, payload: EvaluateRequest) -> ApplyResponse:
        active = await self._determine_active(world_id, payload)
        return ApplyResponse(active=active)

    async def apply(
        self,
        world_id: str,
        payload: ApplyRequest,
        gating: GatingPolicy | None,
    ) -> ApplyAck:
        pre_disable: List[str] = []
        post_enable: List[str] = []
        if isinstance(gating, GatingPolicy):
            try:
                pre_disable = self._coerce_edge_targets(gating.edges.pre_promotion.disable_edges_to)
                post_enable = self._coerce_edge_targets(gating.edges.post_promotion.enable_edges_to)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

        lock = self._lock_for(world_id)
        async with lock:
            state = self.apply_runs.get(world_id)
            if state:
                if not state.get("completed", False):
                    stage = state.get("stage")
                    if state.get("run_id") == payload.run_id:
                        if stage == "rolled_back":
                            return ApplyAck(
                                ok=False,
                                run_id=payload.run_id,
                                active=list(state.get("active", [])),
                                phase=stage,
                            )
                        return ApplyAck(
                            run_id=payload.run_id,
                            active=list(state.get("active", [])),
                            phase=stage,
                        )
                    if stage == "rolled_back":
                        self.apply_runs.pop(world_id, None)
                        state = None
                    else:
                        raise HTTPException(status_code=409, detail="apply in progress")
                elif state.get("run_id") == payload.run_id:
                    return ApplyAck(
                        run_id=payload.run_id,
                        active=list(state.get("active", [])),
                        phase="completed",
                    )

            target_active = await self._determine_active(world_id, payload)
            previous_decisions = list(await self.store.get_decisions(world_id))
            snapshot_full = await self.store.snapshot_activation(world_id)
            snapshot_view = {
                "state": {
                    sid: {side: dict(entry) for side, entry in sides.items()}
                    for sid, sides in snapshot_full.state.items()
                }
            }
            run_state: Dict[str, Any] = {
                "run_id": payload.run_id,
                "stage": "requested",
                "completed": False,
                "sequence": 0,
                "active": list(target_active),
            }
            self.apply_runs[world_id] = run_state

            await self.store.record_apply_stage(
                world_id,
                payload.run_id,
                "requested",
                plan=payload.plan.model_dump() if payload.plan else None,
                active=list(target_active),
                gating_policy=gating.model_dump() if isinstance(gating, GatingPolicy) else None,
            )

            edge_restore: Dict[tuple[str, str], Dict[str, Any] | None] = {}

            async def _set_edge_override(domain: str, *, active: bool, reason: str | None) -> None:
                src_node_id = "domain:backtest"
                dst_node_id = f"domain:{domain}"
                key = (src_node_id, dst_node_id)
                if key not in edge_restore:
                    edge_restore[key] = await self.store.get_edge_override(world_id, src_node_id, dst_node_id)
                await self.store.upsert_edge_override(
                    world_id,
                    src_node_id,
                    dst_node_id,
                    active=active,
                    reason=reason,
                )

            async def _restore_edge_overrides() -> None:
                if not edge_restore:
                    return
                for (src_node_id, dst_node_id), previous in edge_restore.items():
                    if previous is None:
                        await self.store.delete_edge_override(world_id, src_node_id, dst_node_id)
                    else:
                        await self.store.upsert_edge_override(
                            world_id,
                            src_node_id,
                            dst_node_id,
                            active=bool(previous.get("active", False)),
                            reason=previous.get("reason"),
                        )

            try:
                if isinstance(gating, GatingPolicy):
                    for domain in pre_disable:
                        await _set_edge_override(
                            domain,
                            active=False,
                            reason=f"pre_promotion_disable:{payload.run_id}",
                        )

                await self._freeze_world(world_id, payload.run_id, snapshot_view, run_state)
                run_state["stage"] = "freeze"
                await self.store.record_apply_stage(world_id, payload.run_id, "freeze")

                await self.store.set_decisions(world_id, list(target_active))
                run_state["stage"] = "switch"
                await self.store.record_apply_stage(
                    world_id,
                    payload.run_id,
                    "switch",
                    active=list(target_active),
                )

                version = await self.store.default_policy_version(world_id)
                if self.bus:
                    sorted_active = sorted(target_active)
                    digest_payload = json.dumps(sorted_active).encode()
                    checksum = hash_bytes(digest_payload)
                    ts = datetime.now(timezone.utc).isoformat()
                    await self.bus.publish_policy_update(
                        world_id,
                        policy_version=version,
                        checksum=checksum,
                        status="ACTIVE",
                        ts=ts,
                        version=version,
                    )

                await self._unfreeze_world(world_id, payload.run_id, snapshot_view, run_state, target_active)
                run_state["stage"] = "unfreeze"
                await self.store.record_apply_stage(world_id, payload.run_id, "unfreeze")

                if isinstance(gating, GatingPolicy):
                    for domain in post_enable:
                        await _set_edge_override(
                            domain,
                            active=True,
                            reason=f"post_promotion_enable:{payload.run_id}",
                        )

                run_state["completed"] = True
                run_state["stage"] = "completed"
                await self.store.record_apply_stage(world_id, payload.run_id, "completed")
                return ApplyAck(run_id=payload.run_id, active=list(target_active), phase="completed")
            except HTTPException:
                await _restore_edge_overrides()
                raise
            except Exception as exc:  # pragma: no cover - defensive fallback
                await self.store.restore_activation(world_id, snapshot_full)
                await self.store.set_decisions(world_id, list(previous_decisions))
                await self.store.record_apply_stage(
                    world_id,
                    payload.run_id,
                    "rolled_back",
                    error=str(exc),
                    active=list(previous_decisions),
                )
                restored = await self.store.snapshot_activation(world_id)
                await self._freeze_world(
                    world_id,
                    payload.run_id,
                    {
                        "state": {
                            sid: {side: dict(entry) for side, entry in sides.items()}
                            for sid, sides in restored.state.items()
                        }
                    },
                    run_state,
                )
                run_state["active"] = list(previous_decisions)
                run_state["stage"] = "rolled_back"
                run_state["completed"] = False
                await _restore_edge_overrides()
                raise HTTPException(status_code=500, detail="apply failed") from exc

    async def upsert_activation(self, world_id: str, payload: ActivationRequest) -> ActivationEnvelope:
        version, data = await self.store.update_activation(
            world_id, payload.model_dump(exclude_unset=True)
        )
        if self.bus:
            full_state = await self.store.get_activation(world_id)
            state_payload = json.dumps(full_state, sort_keys=True).encode()
            state_hash = hash_bytes(state_payload)
            await self.bus.publish_activation_update(
                world_id,
                etag=data.get("etag", str(version)),
                run_id=str(data.get("run_id") or ""),
                ts=str(data.get("ts")),
                state_hash=state_hash,
                payload={
                    key: val
                    for key, val in {
                        **data,
                        "strategy_id": payload.strategy_id,
                        "side": payload.side,
                    }.items()
                    if key not in {"etag", "run_id", "ts"} and val is not None
                },
                version=version,
            )
        return ActivationEnvelope(
            world_id=world_id,
            strategy_id=payload.strategy_id,
            side=payload.side,
            **data,
        )

    @staticmethod
    def augment_metrics_with_linearity(
        metrics: Dict[str, Dict[str, float]],
        series: Dict[str, StrategySeries] | None,
    ) -> Dict[str, Dict[str, float]]:
        if not series:
            return metrics
        out: Dict[str, Dict[str, float]] = {k: dict(v) for k, v in (metrics or {}).items()}

        equities: Dict[str, List[float]] = {}
        for sid, s in series.items():
            eq: List[float] | None
            if s.equity:
                eq = list(s.equity)
            elif s.pnl:
                eq = list(s.pnl)
            elif s.returns:
                cumulative = 0.0
                eq = []
                for value in s.returns:
                    cumulative += float(value)
                    eq.append(cumulative)
            else:
                eq = None
            if eq and len(eq) >= 2:
                equities[sid] = eq
                m1 = equity_linearity_metrics(eq)
                m2 = equity_linearity_metrics_v2(eq)
                slot = out.setdefault(sid, {})
                slot.update(
                    {
                        "el_v1_score": m1["score"],
                        "el_v1_r2_up": m1["r2_up"],
                        "el_v1_straightness": m1["straightness_ratio"],
                        "el_v1_monotonicity": m1["monotonicity"],
                        "el_v1_new_high_frac": m1["new_high_frac"],
                        "el_v1_net_gain": m1["net_gain"],
                        "el_v2_score": m2["score"],
                        "el_v2_tvr": m2["tvr"],
                        "el_v2_tuw": m2["tuw"],
                        "el_v2_r2_up": m2["r2_up"],
                        "el_v2_spearman_rho": m2["spearman_rho"],
                        "el_v2_t_slope": m2["t_slope"],
                        "el_v2_t_slope_sig": m2["t_slope_sig"],
                        "el_v2_mdd_norm": m2["mdd_norm"],
                        "el_v2_net_gain": m2["net_gain"],
                    }
                )

        if equities:
            minlen = min(len(v) for v in equities.values())
            if minlen >= 2:
                portfolio = [sum(v[i] for v in equities.values()) for i in range(minlen)]
                p1 = equity_linearity_metrics(portfolio)
                p2 = equity_linearity_metrics_v2(portfolio)
                for sid in equities.keys():
                    slot = out.setdefault(sid, {})
                    slot.update(
                        {
                            "portfolio_el_v1_score": p1["score"],
                            "portfolio_el_v2_score": p2["score"],
                            "portfolio_el_v2_tvr": p2["tvr"],
                            "portfolio_el_v2_tuw": p2["tuw"],
                            "portfolio_el_v2_mdd_norm": p2["mdd_norm"],
                        }
                    )

        return out

    def _lock_for(self, world_id: str) -> asyncio.Lock:
        lock = self.apply_locks.get(world_id)
        if lock is None:
            lock = asyncio.Lock()
            self.apply_locks[world_id] = lock
        return lock

    def _next_sequence(self, state: Dict[str, Any]) -> int:
        state["sequence"] = int(state.get("sequence", 0)) + 1
        return state["sequence"]

    def _coerce_edge_targets(self, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            candidates: Iterable[str] = [value]
        else:
            candidates = list(value)
        normalized = {self._normalize_edge_domain(item) for item in candidates}
        return sorted(normalized)

    def _normalize_edge_domain(self, candidate: str) -> str:
        domain = str(candidate).strip().lower()
        if not domain:
            raise ValueError("edge override domain cannot be empty")
        if domain not in EXECUTION_DOMAINS:
            raise ValueError(f"unknown execution domain for edge override: {candidate}")
        return domain

    async def _determine_active(
        self,
        world_id: str,
        payload: ApplyRequest | EvaluateRequest,
    ) -> List[str]:
        if isinstance(payload, ApplyRequest) and payload.plan:
            prev = payload.previous or await self.store.get_decisions(world_id)
            activate = set(payload.plan.activate)
            deactivate = set(payload.plan.deactivate)
            return sorted((set(prev) - deactivate) | activate)

        policy = payload.policy or await self.store.get_default_policy(world_id)
        if policy is None:
            raise HTTPException(status_code=404, detail="policy not found")
        prev = payload.previous or await self.store.get_decisions(world_id)
        metrics = self.augment_metrics_with_linearity(
            payload.metrics or {}, getattr(payload, "series", None)
        )
        return evaluate_policy(metrics, policy, prev, payload.correlations)

    async def _update_activation_state(
        self,
        world_id: str,
        payload: Dict[str, Any],
        *,
        phase: str | None = None,
        requires_ack: bool = False,
        sequence: int | None = None,
    ) -> Dict[str, Any]:
        version, data = await self.store.update_activation(world_id, payload)
        if self.bus:
            full_state = await self.store.get_activation(world_id)
            state_payload = json.dumps(full_state, sort_keys=True).encode()
            state_hash = hash_bytes(state_payload)
            event_payload = {
                key: val
                for key, val in {
                    **data,
                    "strategy_id": payload["strategy_id"],
                    "side": payload["side"],
                    "phase": phase,
                }.items()
                if key not in {"etag", "run_id", "ts"} and val is not None
            }
            await self.bus.publish_activation_update(
                world_id,
                etag=data.get("etag", str(version)),
                run_id=str(data.get("run_id") or ""),
                ts=str(data.get("ts")),
                state_hash=state_hash,
                payload=event_payload,
                version=version,
                requires_ack=requires_ack,
                sequence=sequence,
            )
        return data

    async def _freeze_world(
        self,
        world_id: str,
        run_id: str,
        snapshot: Dict[str, Any],
        run_state: Dict[str, Any],
    ) -> None:
        state = snapshot.get("state", {})
        if not state:
            return
        for strategy_id, sides in state.items():
            for side, entry in sides.items():
                payload = {
                    "strategy_id": strategy_id,
                    "side": side,
                    "active": False,
                    "weight": entry.get("weight", 0.0),
                    "freeze": True,
                    "drain": True,
                    "effective_mode": entry.get("effective_mode"),
                    "run_id": run_id,
                }
                sequence = self._next_sequence(run_state)
                await self._update_activation_state(
                    world_id,
                    payload,
                    phase="freeze",
                    requires_ack=True,
                    sequence=sequence,
                )

    async def _unfreeze_world(
        self,
        world_id: str,
        run_id: str,
        snapshot: Dict[str, Any],
        run_state: Dict[str, Any],
        target_active: Sequence[str],
    ) -> None:
        state = snapshot.get("state", {})
        active_set = set(target_active)
        seen: set[tuple[str, str]] = set()
        for strategy_id, sides in state.items():
            for side, entry in sides.items():
                seen.add((strategy_id, side))
                active_flag = strategy_id in active_set
                payload = {
                    "strategy_id": strategy_id,
                    "side": side,
                    "active": active_flag,
                    "weight": entry.get("weight", 1.0 if active_flag else 0.0),
                    "freeze": False,
                    "drain": False,
                    "effective_mode": entry.get("effective_mode"),
                    "run_id": run_id,
                }
                sequence = self._next_sequence(run_state)
                await self._update_activation_state(
                    world_id,
                    payload,
                    phase="unfreeze",
                    requires_ack=True,
                    sequence=sequence,
                )

        for strategy_id in active_set:
            if all(strategy_id != sid for sid, _ in seen):
                sequence = self._next_sequence(run_state)
                await self._update_activation_state(
                    world_id,
                    {
                        "strategy_id": strategy_id,
                        "side": "long",
                        "active": True,
                        "weight": 1.0,
                        "freeze": False,
                        "drain": False,
                        "run_id": run_id,
                    },
                    phase="unfreeze",
                    requires_ack=True,
                    sequence=sequence,
                )


__all__ = ["WorldService"]
