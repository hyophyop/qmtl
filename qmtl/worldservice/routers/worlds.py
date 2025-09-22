from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Response

from ..schemas import (
    EdgeOverrideResponse,
    EdgeOverrideUpsertRequest,
    World,
    WorldNodeRef,
    WorldNodeUpsertRequest,
)
from ..services import WorldService


def create_worlds_router(service: WorldService) -> APIRouter:
    router = APIRouter()
    store = service.store

    @router.post('/worlds', status_code=201)
    async def post_world(payload: World) -> World:
        await store.create_world(payload.model_dump())
        return payload

    @router.get('/worlds')
    async def get_worlds() -> List[Dict]:
        return await store.list_worlds()

    @router.get('/worlds/{world_id}')
    async def get_world(world_id: str) -> Dict:
        world = await store.get_world(world_id)
        if not world:
            raise HTTPException(status_code=404, detail='world not found')
        return world

    @router.put('/worlds/{world_id}')
    async def put_world(world_id: str, payload: World) -> Dict:
        await store.update_world(world_id, payload.model_dump())
        world = await store.get_world(world_id)
        if not world:
            raise HTTPException(status_code=404, detail='world not found')
        return world

    @router.delete('/worlds/{world_id}', status_code=204)
    async def delete_world(world_id: str) -> Response:
        await store.delete_world(world_id)
        return Response(status_code=204)

    @router.get('/worlds/{world_id}/nodes', response_model=List[WorldNodeRef])
    async def get_world_nodes(world_id: str, execution_domain: str | None = None) -> List[WorldNodeRef]:
        try:
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
            node = await store.get_world_node(world_id, node_id, execution_domain=execution_domain)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not node:
            raise HTTPException(status_code=404, detail='world node not found')
        return WorldNodeRef(**node)

    @router.put('/worlds/{world_id}/nodes/{node_id}', response_model=WorldNodeRef)
    async def put_world_node(world_id: str, node_id: str, payload: WorldNodeUpsertRequest) -> WorldNodeRef:
        try:
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
            await store.delete_world_node(world_id, node_id, execution_domain=execution_domain)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return Response(status_code=204)

    @router.get('/worlds/{world_id}/edges/overrides', response_model=List[EdgeOverrideResponse])
    async def get_edge_overrides(world_id: str) -> List[EdgeOverrideResponse]:
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
        override = await store.upsert_edge_override(
            world_id,
            src_node_id,
            dst_node_id,
            **kwargs,
        )
        return EdgeOverrideResponse(**override)

    @router.get('/worlds/{world_id}/audit')
    async def get_audit(world_id: str) -> List[Dict]:
        return await store.get_audit(world_id)

    return router
