from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Response

from ..schemas import (
    BindingsResponse,
    DecisionEnvelope,
    DecisionsRequest,
    SeamlessArtifactPayload,
)
from ..services import WorldService
from qmtl.foundation.common.compute_context import canonicalize_world_mode


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
        decision = await service.decide(world_id)
        response.headers['Cache-Control'] = 'max-age=300'
        return decision

    @router.post('/worlds/{world_id}/decisions', response_model=BindingsResponse)
    async def post_decisions(world_id: str, payload: DecisionsRequest) -> BindingsResponse:
        store = service.store
        await store.set_decisions(world_id, payload.strategies)
        strategies = await store.get_decisions(world_id)
        return BindingsResponse(strategies=strategies)

    @router.get('/worlds/{world_id}/decisions', response_model=BindingsResponse)
    async def get_decisions(world_id: str) -> BindingsResponse:
        store = service.store
        strategies = await store.get_decisions(world_id)
        return BindingsResponse(strategies=strategies)

    return router
