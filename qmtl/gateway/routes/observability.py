from __future__ import annotations

from fastapi import APIRouter, Response

from qmtl.gateway import metrics as gw_metrics


def create_router() -> APIRouter:
    router = APIRouter()

    @router.get("/metrics")
    async def metrics_endpoint() -> Response:
        return Response(gw_metrics.collect_metrics(), media_type="text/plain")

    return router


__all__ = ["create_router"]
