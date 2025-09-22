from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from qmtl.gateway.dagmanager_client import DagManagerClient
from qmtl.gateway.degradation import DegradationManager
from qmtl.gateway.strategy_manager import StrategyManager
from qmtl.gateway.submission import SubmissionPipeline
from qmtl.gateway.ws import WebSocketHub
from qmtl.gateway.world_client import WorldServiceClient

from .dependencies import GatewayDependencyProvider
from .fills import create_router as create_fills_router
from .observability import create_router as create_observability_router
from .status import create_router as create_status_router
from .strategies import create_router as create_strategies_router
from .worlds import create_router as create_worlds_router


def create_api_router(
    manager: StrategyManager,
    redis_conn: Any,
    database_obj: Any,
    dagmanager: DagManagerClient,
    ws_hub: Optional[WebSocketHub],
    degradation: DegradationManager,
    world_client: Optional[WorldServiceClient],
    enforce_live_guard: bool,
    fill_producer: Any | None = None,
    submission_pipeline: SubmissionPipeline | None = None,
) -> APIRouter:
    deps = GatewayDependencyProvider(
        manager=manager,
        redis_conn=redis_conn,
        database_obj=database_obj,
        dagmanager=dagmanager,
        ws_hub=ws_hub,
        degradation=degradation,
        world_client=world_client,
        enforce_live_guard=enforce_live_guard,
        fill_producer=fill_producer,
        submission_pipeline=submission_pipeline,
    )

    router = APIRouter()
    router.include_router(create_status_router(deps))
    router.include_router(create_strategies_router(deps))
    router.include_router(create_worlds_router(deps))
    router.include_router(create_fills_router(deps))
    router.include_router(create_observability_router())
    return router


__all__ = ["create_api_router", "JSONResponse"]
