from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict

from fastapi import APIRouter, Response

from ..schemas import BindingsResponse, DecisionEnvelope, DecisionsRequest
from ..services import WorldService


def create_bindings_router(service: WorldService) -> APIRouter:
    router = APIRouter()

    @router.post('/worlds/{world_id}/bindings', response_model=BindingsResponse)
    async def post_bindings(world_id: str, payload: DecisionsRequest) -> BindingsResponse:
        store = service.store
        await store.add_bindings(world_id, payload.strategies)
        strategies = await store.list_bindings(world_id)
        return BindingsResponse(strategies=strategies)

    @router.get('/worlds/{world_id}/bindings', response_model=BindingsResponse)
    async def get_bindings(world_id: str) -> BindingsResponse:
        store = service.store
        strategies = await store.list_bindings(world_id)
        return BindingsResponse(strategies=strategies)

    @router.get('/worlds/{world_id}/decide', response_model=DecisionEnvelope)
    async def get_decide(world_id: str, response: Response) -> DecisionEnvelope:
        store = service.store
        version = await store.default_policy_version(world_id)
        now = datetime.now(timezone.utc)
        strategies = await store.get_decisions(world_id)
        effective_mode = 'active' if strategies else 'validate'
        reason = 'policy_evaluated' if strategies else 'no_active_strategies'
        ttl = '300s'
        etag = f"w:{world_id}:v{version}:{int(now.timestamp())}"
        response.headers['Cache-Control'] = 'max-age=300'
        return DecisionEnvelope(
            world_id=world_id,
            policy_version=version,
            effective_mode=effective_mode,
            reason=reason,
            as_of=now.replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
            ttl=ttl,
            etag=etag,
        )

    @router.post('/worlds/{world_id}/decisions')
    async def post_decisions(world_id: str, payload: DecisionsRequest) -> Dict:
        store = service.store
        await store.set_decisions(world_id, payload.strategies)
        return {'strategies': payload.strategies}

    return router
