from __future__ import annotations

import logging
from typing import Dict, List

from fastapi import APIRouter, HTTPException

from ..policy_engine import Policy
from ..schemas import PolicyRequest, PolicyVersionResponse
from ..services import WorldService

logger = logging.getLogger(__name__)


def create_policies_router(service: WorldService) -> APIRouter:
    router = APIRouter()

    @router.post('/worlds/{world_id}/policies', response_model=PolicyVersionResponse)
    async def post_policy(world_id: str, payload: PolicyRequest) -> PolicyVersionResponse:
        store = service.store
        version = await store.add_policy(world_id, payload.policy)
        return PolicyVersionResponse(version=version)

    @router.get('/worlds/{world_id}/policies')
    async def get_policies(world_id: str) -> List[Dict]:
        store = service.store
        return await store.list_policies(world_id)

    @router.get('/worlds/{world_id}/policies/{version}')
    async def get_policy(world_id: str, version: int) -> Dict:
        store = service.store
        policy_payload = await store.get_policy(world_id, version)
        if not policy_payload:
            raise HTTPException(status_code=404, detail='policy not found')

        if isinstance(policy_payload, Policy):
            return policy_payload.model_dump()

        if isinstance(policy_payload, dict):
            raw = policy_payload.get("policy", policy_payload)
            try:
                model = Policy.model_validate(raw)
                return model.model_dump()
            except Exception:
                return raw

        return {"policy": policy_payload}

    @router.post('/worlds/{world_id}/set-default')
    async def post_set_default(world_id: str, payload: PolicyVersionResponse) -> PolicyVersionResponse:
        store = service.store
        await store.set_default_policy(world_id, payload.version)
        if service.bus is not None:
            try:
                await service.bus.publish_validation_profile_changed(
                    world_id,
                    policy_version=payload.version,
                )
            except Exception:  # pragma: no cover - best-effort observability
                logger.exception(
                    "Failed to publish validation profile changed event for %s",
                    world_id,
                )
        return payload

    return router
