from __future__ import annotations

import json
from fastapi import APIRouter, HTTPException, Response

from qmtl.common.hashutils import hash_bytes

from ..policy import parse_gating_policy
from ..schemas import (
    ActivationEnvelope,
    ActivationRequest,
    ApplyAck,
    ApplyRequest,
    ApplyResponse,
    EvaluateRequest,
)
from ..services import WorldService


def create_activation_router(service: WorldService) -> APIRouter:
    router = APIRouter()

    @router.get('/worlds/{world_id}/activation', response_model=ActivationEnvelope)
    async def get_activation(
        world_id: str, strategy_id: str, side: str, response: Response
    ) -> ActivationEnvelope:
        store = service.store
        data = await store.get_activation(world_id, strategy_id=strategy_id, side=side)
        if 'etag' not in data:
            raise HTTPException(status_code=404, detail='activation not found')
        response.headers['ETag'] = data['etag']
        filtered = {key: value for key, value in data.items() if key != 'version'}
        return ActivationEnvelope(
            world_id=world_id,
            strategy_id=strategy_id,
            side=side,
            **filtered,
        )

    @router.put('/worlds/{world_id}/activation', response_model=ActivationEnvelope)
    async def put_activation(
        world_id: str, payload: ActivationRequest, response: Response
    ) -> ActivationEnvelope:
        envelope = await service.upsert_activation(world_id, payload)
        response.headers['ETag'] = envelope.etag
        return envelope

    @router.post('/worlds/{world_id}/evaluate', response_model=ApplyResponse)
    async def post_evaluate(world_id: str, payload: EvaluateRequest) -> ApplyResponse:
        return await service.evaluate(world_id, payload)

    @router.post('/worlds/{world_id}/apply', response_model=ApplyAck)
    async def post_apply(world_id: str, payload: ApplyRequest) -> ApplyAck:
        gating = None
        if payload.gating_policy is not None:
            try:
                gating = parse_gating_policy(payload.gating_policy)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        return await service.apply(world_id, payload, gating)

    @router.get('/worlds/{world_id}/{topic}/state_hash')
    async def get_state_hash(world_id: str, topic: str) -> dict:
        topic_normalized = (topic or '').lower()
        if topic_normalized != 'activation':
            raise HTTPException(status_code=400, detail='unsupported topic')
        store = service.store
        data = await store.get_activation(world_id)
        payload = json.dumps(data, sort_keys=True).encode()
        digest = hash_bytes(payload)
        return {'state_hash': digest}

    return router
