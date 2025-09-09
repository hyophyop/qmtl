from __future__ import annotations

from typing import Dict, List

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

from .policy_engine import Policy, evaluate_policy
from .controlbus_producer import ControlBusProducer
from .storage import Storage


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
    side: str
    active: bool


class ApplyRequest(BaseModel):
    metrics: Dict[str, Dict[str, float]]
    previous: List[str] | None = None
    correlations: Dict[tuple[str, str], float] | None = None
    policy: Policy | None = None


class ApplyResponse(BaseModel):
    active: List[str]


class DecisionsRequest(BaseModel):
    strategies: List[str]


class DecisionsResponse(BaseModel):
    strategies: List[str]


class BindingsResponse(BaseModel):
    strategies: List[str]


class ActivationResponse(BaseModel):
    version: int
    state: Dict | None = None


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

    @app.get('/worlds/{world_id}/decide', response_model=DecisionsResponse)
    async def get_decide(world_id: str) -> DecisionsResponse:
        strategies = await store.get_decisions(world_id)
        return DecisionsResponse(strategies=strategies)

    @app.post('/worlds/{world_id}/decisions', response_model=DecisionsResponse)
    async def post_decisions(world_id: str, payload: DecisionsRequest) -> DecisionsResponse:
        await store.set_decisions(world_id, payload.strategies)
        return DecisionsResponse(strategies=payload.strategies)

    @app.get('/worlds/{world_id}/activation', response_model=ActivationResponse)
    async def get_activation(world_id: str) -> ActivationResponse:
        data = await store.get_activation(world_id)
        return ActivationResponse(version=data['version'], state=data.get('state'))

    @app.put('/worlds/{world_id}/activation', response_model=ActivationResponse)
    async def put_activation(world_id: str, payload: ActivationRequest) -> ActivationResponse:
        version = await store.update_activation(world_id, {payload.side: {'active': payload.active}})
        if bus:
            await bus.publish_activation_update(world_id, {'side': payload.side, 'active': payload.active}, version=version)
        data = await store.get_activation(world_id)
        return ActivationResponse(version=version, state=data.get('state'))

    @app.post('/worlds/{world_id}/evaluate', response_model=ApplyResponse)
    async def post_evaluate(world_id: str, payload: ApplyRequest) -> ApplyResponse:
        policy = payload.policy or await store.get_default_policy(world_id)
        if policy is None:
            raise HTTPException(status_code=404, detail='policy not found')
        prev = payload.previous or await store.get_decisions(world_id)
        active = evaluate_policy(payload.metrics, policy, prev, payload.correlations)
        return ApplyResponse(active=active)

    @app.post('/worlds/{world_id}/apply', response_model=ApplyResponse)
    async def post_apply(world_id: str, payload: ApplyRequest) -> ApplyResponse:
        policy = payload.policy or await store.get_default_policy(world_id)
        if policy is None:
            raise HTTPException(status_code=404, detail='policy not found')
        prev = payload.previous or await store.get_decisions(world_id)
        active = evaluate_policy(payload.metrics, policy, prev, payload.correlations)
        await store.set_decisions(world_id, active)
        version = await store.default_policy_version(world_id)
        if bus:
            await bus.publish_policy_update(world_id, active, version=version)
        return ApplyResponse(active=active)

    @app.get('/worlds/{world_id}/audit')
    async def get_audit(world_id: str) -> List[Dict]:
        return await store.get_audit(world_id)

    return app


__all__ = ['World', 'PolicyRequest', 'ApplyRequest', 'ApplyResponse', 'create_app']
