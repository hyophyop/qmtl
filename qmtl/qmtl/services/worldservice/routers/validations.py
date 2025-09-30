from __future__ import annotations

from fastapi import APIRouter, Response

from ..schemas import (
    ValidationCacheLookupRequest,
    ValidationCacheResponse,
    ValidationCacheStoreRequest,
)
from ..services import WorldService


def create_validations_router(service: WorldService) -> APIRouter:
    router = APIRouter()

    @router.post(
        '/worlds/{world_id}/validations/cache/lookup',
        response_model=ValidationCacheResponse,
    )
    async def post_validation_cache_lookup(
        world_id: str, payload: ValidationCacheLookupRequest
    ) -> ValidationCacheResponse:
        store = service.store
        entry = await store.get_validation_cache(world_id, **payload.model_dump())
        if not entry:
            return ValidationCacheResponse(cached=False)
        return ValidationCacheResponse(
            cached=True,
            eval_key=entry.eval_key,
            result=entry.result,
            metrics=entry.metrics,
            timestamp=entry.timestamp,
        )

    @router.post('/worlds/{world_id}/validations/cache', response_model=ValidationCacheResponse)
    async def post_validation_cache(
        world_id: str, payload: ValidationCacheStoreRequest
    ) -> ValidationCacheResponse:
        store = service.store
        entry = await store.set_validation_cache(world_id, **payload.model_dump())
        return ValidationCacheResponse(
            cached=True,
            eval_key=entry.eval_key,
            result=entry.result,
            metrics=entry.metrics,
            timestamp=entry.timestamp,
        )

    @router.delete('/worlds/{world_id}/validations/{node_id}', status_code=204)
    async def delete_validation_cache(
        world_id: str, node_id: str, execution_domain: str | None = None
    ) -> Response:
        store = service.store
        await store.invalidate_validation_cache(
            world_id, node_id=node_id, execution_domain=execution_domain
        )
        return Response(status_code=204)

    return router
