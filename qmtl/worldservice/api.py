from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Sequence

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from .policy_engine import Policy, evaluate_policy
from .controlbus_producer import ControlBusProducer
from .storage import EXECUTION_DOMAINS, WORLD_NODE_STATUSES, Storage
from .policy import GatingPolicy, parse_gating_policy
from qmtl.common.hashutils import hash_bytes
from qmtl.transforms import (
    equity_linearity_metrics,
    equity_linearity_metrics_v2,
)


ExecutionDomainEnum = Enum(
    "ExecutionDomainEnum",
    {value.upper(): value for value in sorted(EXECUTION_DOMAINS)},
    type=str,
)
WorldNodeStatusEnum = Enum(
    "WorldNodeStatusEnum",
    {value.upper(): value for value in sorted(WORLD_NODE_STATUSES)},
    type=str,
)


class World(BaseModel):
    id: str
    name: str | None = None


class PolicyRequest(BaseModel):
    policy: Policy


class PolicyVersionResponse(BaseModel):
    version: int


class BindingRequest(BaseModel):
    strategies: List[str]


class ActivationRequest(BaseModel):
    strategy_id: str
    side: str
    active: bool
    weight: float | None = None
    freeze: bool | None = None
    drain: bool | None = None
    effective_mode: str | None = None
    run_id: str | None = None
    ts: str | None = None


class ApplyPlan(BaseModel):
    activate: List[str] = Field(default_factory=list)
    deactivate: List[str] = Field(default_factory=list)


class EvaluateRequest(BaseModel):
    metrics: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    previous: List[str] | None = None
    correlations: Dict[tuple[str, str], float] | None = None
    policy: Policy | None = None
    # Optional time series for server-side metric augmentation
    # Each strategy may provide cumulative equity/pnl or returns (to be cumulated)
    series: Dict[str, "StrategySeries"] | None = None


class ApplyRequest(EvaluateRequest):
    run_id: str
    plan: ApplyPlan | None = None
    gating_policy: Any | None = None


class ApplyResponse(BaseModel):
    active: List[str]


class ApplyAck(BaseModel):
    ok: bool = True
    run_id: str
    active: List[str]
    phase: str | None = None


class DecisionsRequest(BaseModel):
    strategies: List[str]


class BindingsResponse(BaseModel):
    strategies: List[str]


class WorldNodeRef(BaseModel):
    world_id: str
    node_id: str
    execution_domain: ExecutionDomainEnum
    status: WorldNodeStatusEnum
    last_eval_key: str | None = None
    annotations: Dict[str, Any] | None = None


class WorldNodeUpsertRequest(BaseModel):
    status: WorldNodeStatusEnum
    execution_domain: ExecutionDomainEnum | None = None
    last_eval_key: str | None = None
    annotations: Dict[str, Any] | None = None


class DecisionEnvelope(BaseModel):
    world_id: str
    policy_version: int
    effective_mode: str
    reason: str | None = None
    as_of: str
    ttl: str
    etag: str


class ActivationEnvelope(BaseModel):
    world_id: str
    strategy_id: str
    side: str
    active: bool
    weight: float
    freeze: bool | None = None
    drain: bool | None = None
    effective_mode: str | None = None
    etag: str
    run_id: str | None = None
    ts: str


def create_app(*, bus: ControlBusProducer | None = None, storage: Storage | None = None) -> FastAPI:
    app = FastAPI()
    store = storage or Storage()
    app.state.apply_locks: Dict[str, asyncio.Lock] = {}
    app.state.apply_runs: Dict[str, Dict[str, Any]] = {}

    def _lock_for(world_id: str) -> asyncio.Lock:
        lock = app.state.apply_locks.get(world_id)
        if lock is None:
            lock = asyncio.Lock()
            app.state.apply_locks[world_id] = lock
        return lock

    def _next_sequence(state: Dict[str, Any]) -> int:
        state["sequence"] = int(state.get("sequence", 0)) + 1
        return state["sequence"]

    async def _update_activation_state(
        world_id: str,
        payload: Dict[str, Any],
        *,
        phase: str | None = None,
        requires_ack: bool = False,
        sequence: int | None = None,
    ) -> Dict[str, Any]:
        version, data = await store.update_activation(world_id, payload)
        if bus:
            full_state = await store.get_activation(world_id)
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
            await bus.publish_activation_update(
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
                sequence = _next_sequence(run_state)
                await _update_activation_state(
                    world_id,
                    payload,
                    phase="freeze",
                    requires_ack=True,
                    sequence=sequence,
                )

    async def _unfreeze_world(
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
                sequence = _next_sequence(run_state)
                await _update_activation_state(
                    world_id,
                    payload,
                    phase="unfreeze",
                    requires_ack=True,
                    sequence=sequence,
                )

        for strategy_id in active_set:
            if all(strategy_id != sid for sid, _ in seen):
                sequence = _next_sequence(run_state)
                await _update_activation_state(
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

    async def _determine_active(world_id: str, payload: ApplyRequest | EvaluateRequest) -> List[str]:
        if isinstance(payload, ApplyRequest) and payload.plan:
            prev = payload.previous or await store.get_decisions(world_id)
            activate = set(payload.plan.activate)
            deactivate = set(payload.plan.deactivate)
            return sorted((set(prev) - deactivate) | activate)

        policy = payload.policy or await store.get_default_policy(world_id)
        if policy is None:
            raise HTTPException(status_code=404, detail="policy not found")
        prev = payload.previous or await store.get_decisions(world_id)
        metrics = _augment_metrics_with_linearity(payload.metrics or {}, getattr(payload, "series", None))
        return evaluate_policy(metrics, policy, prev, payload.correlations)

    @app.post('/worlds', status_code=201)
    async def post_world(payload: World) -> World:
        await store.create_world(payload.model_dump())
        return payload

    @app.get('/worlds')
    async def get_worlds() -> List[Dict]:
        return await store.list_worlds()

    @app.get('/worlds/{world_id}')
    async def get_world(world_id: str) -> Dict:
        w = await store.get_world(world_id)
        if not w:
            raise HTTPException(status_code=404, detail='world not found')
        return w

    @app.put('/worlds/{world_id}')
    async def put_world(world_id: str, payload: World) -> Dict:
        await store.update_world(world_id, payload.model_dump())
        w = await store.get_world(world_id)
        if not w:
            raise HTTPException(status_code=404, detail='world not found')
        return w

    @app.delete('/worlds/{world_id}', status_code=204)
    async def delete_world(world_id: str) -> Response:
        await store.delete_world(world_id)
        return Response(status_code=204)

    @app.get('/worlds/{world_id}/nodes', response_model=List[WorldNodeRef])
    async def get_world_nodes(world_id: str, execution_domain: str | None = None) -> List[WorldNodeRef]:
        try:
            nodes = await store.list_world_nodes(world_id, execution_domain=execution_domain)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return [WorldNodeRef(**node) for node in nodes]

    @app.get('/worlds/{world_id}/nodes/{node_id}', response_model=WorldNodeRef)
    async def get_world_node(
        world_id: str,
        node_id: str,
        execution_domain: str | None = None,
    ) -> WorldNodeRef:
        try:
            node = await store.get_world_node(world_id, node_id, execution_domain=execution_domain)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not node:
            raise HTTPException(status_code=404, detail='world node not found')
        return WorldNodeRef(**node)

    @app.put('/worlds/{world_id}/nodes/{node_id}', response_model=WorldNodeRef)
    async def put_world_node(world_id: str, node_id: str, payload: WorldNodeUpsertRequest) -> WorldNodeRef:
        try:
            node = await store.upsert_world_node(
                world_id,
                node_id,
                execution_domain=payload.execution_domain.value if payload.execution_domain else None,
                status=payload.status.value,
                last_eval_key=payload.last_eval_key,
                annotations=payload.annotations,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return WorldNodeRef(**node)

    @app.delete('/worlds/{world_id}/nodes/{node_id}', status_code=204)
    async def delete_world_node(
        world_id: str,
        node_id: str,
        execution_domain: str | None = None,
    ) -> Response:
        try:
            await store.delete_world_node(world_id, node_id, execution_domain=execution_domain)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return Response(status_code=204)

    @app.post('/worlds/{world_id}/policies', response_model=PolicyVersionResponse)
    async def post_policy(world_id: str, payload: PolicyRequest) -> PolicyVersionResponse:
        version = await store.add_policy(world_id, payload.policy)
        return PolicyVersionResponse(version=version)

    @app.get('/worlds/{world_id}/policies')
    async def get_policies(world_id: str) -> List[Dict]:
        return await store.list_policies(world_id)

    @app.get('/worlds/{world_id}/policies/{version}')
    async def get_policy(world_id: str, version: int) -> Dict:
        policy = await store.get_policy(world_id, version)
        if not policy:
            raise HTTPException(status_code=404, detail='policy not found')
        return policy.model_dump()

    @app.post('/worlds/{world_id}/set-default')
    async def post_set_default(world_id: str, payload: PolicyVersionResponse) -> PolicyVersionResponse:
        await store.set_default_policy(world_id, payload.version)
        return payload

    @app.post('/worlds/{world_id}/bindings', response_model=BindingsResponse)
    async def post_bindings(world_id: str, payload: BindingRequest) -> BindingsResponse:
        await store.add_bindings(world_id, payload.strategies)
        strategies = await store.list_bindings(world_id)
        return BindingsResponse(strategies=strategies)

    @app.get('/worlds/{world_id}/bindings', response_model=BindingsResponse)
    async def get_bindings(world_id: str) -> BindingsResponse:
        strategies = await store.list_bindings(world_id)
        return BindingsResponse(strategies=strategies)

    @app.get('/worlds/{world_id}/decide', response_model=DecisionEnvelope)
    async def get_decide(world_id: str, response: Response) -> DecisionEnvelope:
        version = await store.default_policy_version(world_id)
        now = datetime.now(timezone.utc)
        strategies = await store.get_decisions(world_id)
        effective_mode = 'active' if strategies else 'validate'
        reason = 'policy_evaluated' if strategies else 'no_active_strategies'
        ttl = '300s'
        etag = f"w:{world_id}:v{version}:{int(now.timestamp())}"
        response.headers["Cache-Control"] = "max-age=300"
        return DecisionEnvelope(
            world_id=world_id,
            policy_version=version,
            effective_mode=effective_mode,
            reason=reason,
            as_of=now.replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
            ttl=ttl,
            etag=etag,
        )

    @app.post('/worlds/{world_id}/decisions')
    async def post_decisions(world_id: str, payload: DecisionsRequest) -> Dict:
        await store.set_decisions(world_id, payload.strategies)
        return {"strategies": payload.strategies}

    @app.get('/worlds/{world_id}/activation', response_model=ActivationEnvelope)
    async def get_activation(world_id: str, strategy_id: str, side: str, response: Response) -> ActivationEnvelope:
        data = await store.get_activation(world_id, strategy_id=strategy_id, side=side)
        if "etag" not in data:
            raise HTTPException(status_code=404, detail='activation not found')
        response.headers["ETag"] = data["etag"]
        filtered = {k: v for k, v in data.items() if k != 'version'}
        return ActivationEnvelope(world_id=world_id, strategy_id=strategy_id, side=side, **filtered)

    @app.put('/worlds/{world_id}/activation', response_model=ActivationEnvelope)
    async def put_activation(world_id: str, payload: ActivationRequest, response: Response) -> ActivationEnvelope:
        version, data = await store.update_activation(world_id, payload.model_dump(exclude_unset=True))
        if bus:
            # Compute state hash similar to the `/state_hash` endpoint for audit
            full_state = await store.get_activation(world_id)
            state_payload = json.dumps(full_state, sort_keys=True).encode()
            state_hash = hash_bytes(state_payload)
            await bus.publish_activation_update(
                world_id,
                etag=data.get('etag', str(version)),
                run_id=str(data.get('run_id') or ''),
                ts=str(data.get('ts')),
                state_hash=state_hash,
                payload={key: val for key, val in {**data, 'strategy_id': payload.strategy_id, 'side': payload.side}.items() if key not in ('etag', 'run_id', 'ts')},
                version=version,
            )
        response.headers["ETag"] = data["etag"]
        return ActivationEnvelope(world_id=world_id, strategy_id=payload.strategy_id, side=payload.side, **data)

    @app.post('/worlds/{world_id}/evaluate', response_model=ApplyResponse)
    async def post_evaluate(world_id: str, payload: EvaluateRequest) -> ApplyResponse:
        active = await _determine_active(world_id, payload)
        return ApplyResponse(active=active)

    @app.post('/worlds/{world_id}/apply', response_model=ApplyAck)
    async def post_apply(world_id: str, payload: ApplyRequest) -> ApplyAck:
        try:
            gating = (
                parse_gating_policy(payload.gating_policy)
                if payload.gating_policy is not None
                else None
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        lock = _lock_for(world_id)
        async with lock:
            state = app.state.apply_runs.get(world_id)
            if state:
                if not state.get("completed", False):
                    stage = state.get("stage")
                    if state.get("run_id") == payload.run_id:
                        if stage == "rolled_back":
                            return ApplyAck(ok=False, run_id=payload.run_id, active=list(state.get("active", [])), phase=stage)
                        return ApplyAck(run_id=payload.run_id, active=list(state.get("active", [])), phase=stage)
                    if stage == "rolled_back":
                        app.state.apply_runs.pop(world_id, None)
                        state = None
                    else:
                        raise HTTPException(status_code=409, detail="apply in progress")
                elif state.get("run_id") == payload.run_id:
                    return ApplyAck(run_id=payload.run_id, active=list(state.get("active", [])), phase="completed")

            target_active = await _determine_active(world_id, payload)
            previous_decisions = list(await store.get_decisions(world_id))
            snapshot_full = await store.snapshot_activation(world_id)
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
            app.state.apply_runs[world_id] = run_state

            await store.record_apply_stage(
                world_id,
                payload.run_id,
                "requested",
                plan=payload.plan.model_dump() if payload.plan else None,
                active=list(target_active),
                gating_policy=gating.model_dump() if isinstance(gating, GatingPolicy) else None,
            )

            try:
                await _freeze_world(world_id, payload.run_id, snapshot_view, run_state)
                run_state["stage"] = "freeze"
                await store.record_apply_stage(world_id, payload.run_id, "freeze")

                await store.set_decisions(world_id, list(target_active))
                run_state["stage"] = "switch"
                await store.record_apply_stage(world_id, payload.run_id, "switch", active=list(target_active))

                version = await store.default_policy_version(world_id)
                if bus:
                    sorted_active = sorted(target_active)
                    digest_payload = json.dumps(sorted_active).encode()
                    checksum = hash_bytes(digest_payload)
                    ts = datetime.now(timezone.utc).isoformat()
                    await bus.publish_policy_update(
                        world_id,
                        policy_version=version,
                        checksum=checksum,
                        status="ACTIVE",
                        ts=ts,
                        version=version,
                    )

                await _unfreeze_world(world_id, payload.run_id, snapshot_view, run_state, target_active)
                run_state["stage"] = "unfreeze"
                await store.record_apply_stage(world_id, payload.run_id, "unfreeze")

                run_state["completed"] = True
                run_state["stage"] = "completed"
                await store.record_apply_stage(world_id, payload.run_id, "completed")
                return ApplyAck(run_id=payload.run_id, active=list(target_active), phase="completed")
            except HTTPException:
                raise
            except Exception as exc:  # pragma: no cover - defensive fallback
                await store.restore_activation(world_id, snapshot_full)
                await store.set_decisions(world_id, list(previous_decisions))
                await store.record_apply_stage(
                    world_id,
                    payload.run_id,
                    "rolled_back",
                    error=str(exc),
                    active=list(previous_decisions),
                )
                restored = await store.snapshot_activation(world_id)
                await _freeze_world(
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
                raise HTTPException(status_code=500, detail="apply failed") from exc

    @app.get('/worlds/{world_id}/{topic}/state_hash')
    async def get_state_hash(world_id: str, topic: str) -> Dict:
        """Return a lightweight state hash for a topic.

        Currently supports 'activation' by hashing the serialized state dict.
        """
        topic = (topic or '').lower()
        if topic != 'activation':
            raise HTTPException(status_code=400, detail='unsupported topic')
        data = await store.get_activation(world_id)
        # Normalize deterministically
        payload = json.dumps(data, sort_keys=True).encode()
        digest = hash_bytes(payload)
        return {"state_hash": digest}

    @app.get('/worlds/{world_id}/audit')
    async def get_audit(world_id: str) -> List[Dict]:
        return await store.get_audit(world_id)

    return app


__all__ = [
    'World',
    'PolicyRequest',
    'ApplyPlan',
    'EvaluateRequest',
    'ApplyRequest',
    'ApplyResponse',
    'ApplyAck',
    'create_app',
]

# ---------------------------------------------------------------------------
# Helper models and utilities (defined after create_app to avoid forward refs)

class StrategySeries(BaseModel):
    equity: List[float] | None = None
    pnl: List[float] | None = None
    returns: List[float] | None = None


def _augment_metrics_with_linearity(
    metrics: Dict[str, Dict[str, float]],
    series: Dict[str, StrategySeries] | None,
) -> Dict[str, Dict[str, float]]:
    if not series:
        return metrics
    # Local copy to avoid mutating caller structures
    out: Dict[str, Dict[str, float]] = {k: dict(v) for k, v in (metrics or {}).items()}

    # Convert provided series to cumulative equity
    equities: Dict[str, List[float]] = {}
    for sid, s in series.items():
        eq: List[float] | None
        if s.equity:
            eq = list(s.equity)
        elif s.pnl:
            eq = list(s.pnl)
        elif s.returns:
            c = 0.0
            eq = []
            for r in s.returns:
                c += float(r)
                eq.append(c)
        else:
            eq = None
        if eq and len(eq) >= 2:
            equities[sid] = eq
            m1 = equity_linearity_metrics(eq)
            m2 = equity_linearity_metrics_v2(eq)
            slot = out.setdefault(sid, {})
            slot.update(
                {
                    # v1
                    "el_v1_score": m1["score"],
                    "el_v1_r2_up": m1["r2_up"],
                    "el_v1_straightness": m1["straightness_ratio"],
                    "el_v1_monotonicity": m1["monotonicity"],
                    "el_v1_new_high_frac": m1["new_high_frac"],
                    "el_v1_net_gain": m1["net_gain"],
                    # v2
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

    # Aggregate portfolio-level metrics across provided series (equal-sum)
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
