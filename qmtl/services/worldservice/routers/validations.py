from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response

from ..schemas import (
    ValidationCacheLookupRequest,
    ValidationCacheResponse,
    ValidationCacheStoreRequest,
    ValidationInvariantsReport,
)
from ..services import WorldService
from ..storage import ValidationCacheEntry
from ..validation_checks import check_validation_invariants


def create_validations_router(service: WorldService) -> APIRouter:
    router = APIRouter()

    def _coerce_entry(entry: ValidationCacheEntry | dict[str, Any] | None) -> ValidationCacheEntry | None:
        if entry is None:
            return None
        if isinstance(entry, ValidationCacheEntry):
            return entry
        return ValidationCacheEntry(**entry)

    def _translate_domain_error(exc: ValueError) -> None:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        '/worlds/{world_id}/validations/cache/lookup',
        response_model=ValidationCacheResponse,
    )
    async def post_validation_cache_lookup(
        world_id: str, payload: ValidationCacheLookupRequest
    ) -> ValidationCacheResponse:
        store = service.store
        try:
            entry = _coerce_entry(await store.get_validation_cache(world_id, **payload.model_dump()))
        except ValueError as exc:  # e.g., invalid execution_domain
            _translate_domain_error(exc)
        if entry is None:
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
        try:
            entry = _coerce_entry(await store.set_validation_cache(world_id, **payload.model_dump()))
        except ValueError as exc:
            _translate_domain_error(exc)
        if entry is None:
            return ValidationCacheResponse(cached=False)
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
        try:
            await store.invalidate_validation_cache(
                world_id, node_id=node_id, execution_domain=execution_domain
            )
        except ValueError as exc:
            _translate_domain_error(exc)
        return Response(status_code=204)

    @router.get(
        "/worlds/{world_id}/validations/invariants",
        response_model=ValidationInvariantsReport,
    )
    async def get_validation_invariants(
        world_id: str, strategy_id: str | None = None
    ) -> ValidationInvariantsReport:
        world = await service.store.get_world(world_id) or {"id": world_id}
        runs = await service.store.list_evaluation_runs(
            world_id=world_id, strategy_id=strategy_id
        )
        report = check_validation_invariants(world, runs)
        return ValidationInvariantsReport(
            ok=report.ok,
            live_status_failures=report.live_status_failures,
            fail_closed_violations=report.fail_closed_violations,
            approved_overrides=report.approved_overrides,
            validation_health_gaps=report.validation_health_gaps,
        )

    return router
