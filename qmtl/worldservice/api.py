from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, List

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

from .policy_engine import Policy, evaluate_policy
from .controlbus_producer import ControlBusProducer
from .storage import Storage
from qmtl.common.hashutils import hash_bytes
from qmtl.transforms import (
    equity_linearity_metrics,
    equity_linearity_metrics_v2,
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


class ApplyRequest(BaseModel):
    metrics: Dict[str, Dict[str, float]]
    previous: List[str] | None = None
    correlations: Dict[tuple[str, str], float] | None = None
    policy: Policy | None = None
    # Optional time series for server-side metric augmentation
    # Each strategy may provide cumulative equity/pnl or returns (to be cumulated)
    series: Dict[str, "StrategySeries"] | None = None


class ApplyResponse(BaseModel):
    active: List[str]


class DecisionsRequest(BaseModel):
    strategies: List[str]


class BindingsResponse(BaseModel):
    strategies: List[str]


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
    async def post_evaluate(world_id: str, payload: ApplyRequest) -> ApplyResponse:
        policy = payload.policy or await store.get_default_policy(world_id)
        if policy is None:
            raise HTTPException(status_code=404, detail='policy not found')
        prev = payload.previous or await store.get_decisions(world_id)
        metrics = _augment_metrics_with_linearity(payload.metrics or {}, payload.series)
        active = evaluate_policy(metrics, policy, prev, payload.correlations)
        return ApplyResponse(active=active)

    @app.post('/worlds/{world_id}/apply', response_model=ApplyResponse)
    async def post_apply(world_id: str, payload: ApplyRequest) -> ApplyResponse:
        policy = payload.policy or await store.get_default_policy(world_id)
        if policy is None:
            raise HTTPException(status_code=404, detail='policy not found')
        prev = payload.previous or await store.get_decisions(world_id)
        metrics = _augment_metrics_with_linearity(payload.metrics or {}, payload.series)
        active = evaluate_policy(metrics, policy, prev, payload.correlations)
        await store.set_decisions(world_id, active)
        version = await store.default_policy_version(world_id)
        if bus:
            # Hash the active strategy list for a checksum
            sorted_active = sorted(active)
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
        return ApplyResponse(active=active)

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


__all__ = ['World', 'PolicyRequest', 'ApplyRequest', 'ApplyResponse', 'create_app']

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
