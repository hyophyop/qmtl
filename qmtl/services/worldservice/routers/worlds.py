from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Response

from ..schemas import (
    EdgeOverrideResponse,
    EdgeOverrideUpsertRequest,
    SeamlessHistoryRequest,
    World,
    WorldNodeRef,
    WorldNodeUpsertRequest,
)
from ..services import WorldService


def create_worlds_router(service: WorldService) -> APIRouter:
    router = APIRouter()

    @router.post('/worlds', status_code=201)
    async def post_world(payload: World) -> World:
        store = service.store
        await store.create_world(payload.model_dump())
        return payload

    @router.get('/worlds')
    async def get_worlds() -> List[Dict]:
        store = service.store
        return await store.list_worlds()

    @router.get('/worlds/{world_id}')
    async def get_world(world_id: str) -> Dict:
        store = service.store
        world = await store.get_world(world_id)
        if not world:
            raise HTTPException(status_code=404, detail='world not found')
        return world

    @router.put('/worlds/{world_id}')
    async def put_world(world_id: str, payload: World) -> Dict:
        store = service.store
        await store.update_world(world_id, payload.model_dump())
        world = await store.get_world(world_id)
        if not world:
            raise HTTPException(status_code=404, detail='world not found')
        return world

    @router.delete('/worlds/{world_id}', status_code=204)
    async def delete_world(world_id: str) -> Response:
        store = service.store
        await store.delete_world(world_id)
        return Response(status_code=204)

    @router.get('/worlds/{world_id}/nodes', response_model=List[WorldNodeRef])
    async def get_world_nodes(world_id: str, execution_domain: str | None = None) -> List[WorldNodeRef]:
        try:
            store = service.store
            nodes = await store.list_world_nodes(world_id, execution_domain=execution_domain)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return [WorldNodeRef(**node) for node in nodes]

    @router.get('/worlds/{world_id}/nodes/{node_id}', response_model=WorldNodeRef)
    async def get_world_node(
        world_id: str,
        node_id: str,
        execution_domain: str | None = None,
    ) -> WorldNodeRef:
        try:
            store = service.store
            node = await store.get_world_node(world_id, node_id, execution_domain=execution_domain)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not node:
            raise HTTPException(status_code=404, detail='world node not found')
        return WorldNodeRef(**node)

    @router.put('/worlds/{world_id}/nodes/{node_id}', response_model=WorldNodeRef)
    async def put_world_node(world_id: str, node_id: str, payload: WorldNodeUpsertRequest) -> WorldNodeRef:
        try:
            store = service.store
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

    @router.delete('/worlds/{world_id}/nodes/{node_id}', status_code=204)
    async def delete_world_node(
        world_id: str,
        node_id: str,
        execution_domain: str | None = None,
    ) -> Response:
        try:
            store = service.store
            await store.delete_world_node(world_id, node_id, execution_domain=execution_domain)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return Response(status_code=204)

    @router.get('/worlds/{world_id}/edges/overrides', response_model=List[EdgeOverrideResponse])
    async def get_edge_overrides(world_id: str) -> List[EdgeOverrideResponse]:
        store = service.store
        overrides = await store.list_edge_overrides(world_id)
        return [EdgeOverrideResponse(**item) for item in overrides]

    @router.put(
        '/worlds/{world_id}/edges/{src_node_id}/{dst_node_id}',
        response_model=EdgeOverrideResponse,
    )
    async def put_edge_override(
        world_id: str,
        src_node_id: str,
        dst_node_id: str,
        payload: EdgeOverrideUpsertRequest,
    ) -> EdgeOverrideResponse:
        kwargs: Dict[str, Any] = {"active": payload.active}
        if 'reason' in payload.model_fields_set:
            kwargs['reason'] = payload.reason
        store = service.store
        override = await store.upsert_edge_override(
            world_id,
            src_node_id,
            dst_node_id,
            **kwargs,
        )
        return EdgeOverrideResponse(**override)

    @router.get('/worlds/{world_id}/audit')
    async def get_audit(world_id: str) -> List[Dict]:
        store = service.store
        return await store.get_audit(world_id)

    @router.post('/worlds/{world_id}/history', status_code=204)
    async def post_world_history(world_id: str, payload: SeamlessHistoryRequest) -> Response:
        store = service.store
        record = payload.model_dump(exclude_unset=True)
        record.pop('strategy_id', None)
        coverage = record.get('coverage_bounds')
        if isinstance(coverage, tuple):
            record['coverage_bounds'] = list(coverage)
        artifact = record.get('artifact')
        if hasattr(artifact, 'model_dump'):
            record['artifact'] = artifact.model_dump(exclude_unset=True)
        updated = record.get('updated_at')
        if not updated:
            record['updated_at'] = (
                datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace('+00:00', 'Z')
            )
        await store.upsert_history_metadata(world_id, payload.strategy_id, record)
        return Response(status_code=204)

    @router.get('/worlds/{world_id}/history')
    async def get_world_history(world_id: str) -> Dict[str, Any]:
        store = service.store
        entries = await store.list_history_metadata(world_id)
        latest = await store.latest_history_metadata(world_id)
        return {'entries': entries, 'latest': latest}

    return router
