from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, HTTPException

from ..schemas import PolicyRequest, PolicyVersionResponse
from ..services import WorldService


def create_policies_router(service: WorldService) -> APIRouter:
    router = APIRouter()

    @router.post('/worlds/{world_id}/policies', response_model=PolicyVersionResponse)
    async def post_policy(world_id: str, payload: PolicyRequest) -> PolicyVersionResponse:
        store = service.store
        version = await store.add_policy(world_id, payload.to_payload())
        return PolicyVersionResponse(version=version)

    @router.get('/worlds/{world_id}/policies')
    async def get_policies(world_id: str) -> List[Dict]:
        store = service.store
        return await store.list_policies(world_id)

    @router.get('/worlds/{world_id}/policies/{version}')
    async def get_policy(world_id: str, version: int) -> Dict:
        store = service.store
        policy = await store.get_policy(world_id, version)
        if not policy:
            raise HTTPException(status_code=404, detail='policy not found')
        return policy.model_dump()

    @router.post('/worlds/{world_id}/set-default')
    async def post_set_default(world_id: str, payload: PolicyVersionResponse) -> PolicyVersionResponse:
        store = service.store
        await store.set_default_policy(world_id, payload.version)
        return payload

    return router
