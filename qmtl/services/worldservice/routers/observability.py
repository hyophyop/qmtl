from __future__ import annotations

from fastapi import APIRouter, Response

from qmtl.services.worldservice import metrics as ws_metrics


def create_observability_router() -> APIRouter:
    router = APIRouter()

    @router.get("/metrics")
    async def metrics_endpoint() -> Response:
        return Response(ws_metrics.collect_metrics(), media_type="text/plain")

    return router


__all__ = ["create_observability_router"]
