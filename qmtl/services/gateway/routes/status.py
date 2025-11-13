from __future__ import annotations

from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends
from fastapi import params as fastapi_params

from qmtl.services.gateway import metrics as gw_metrics
from qmtl.services.gateway.dagmanager_client import DagManagerClient
from qmtl.services.gateway.degradation import DegradationManager
from qmtl.services.gateway.gateway_health import get_health as gateway_health
from qmtl.services.gateway.world_client import WorldServiceClient

from .dependencies import GatewayDependencyProvider


def _resolve_dependency(value: Any, provider: Callable[[], Any]) -> Any:
    if isinstance(value, fastapi_params.Depends):
        return provider()
    return value


def create_router(deps: GatewayDependencyProvider) -> APIRouter:
    router = APIRouter()

    @router.get("/status")
    async def status_endpoint(
        redis_conn: Any = Depends(deps.provide_redis_conn),
        database_obj: Any = Depends(deps.provide_database),
        dagmanager: DagManagerClient = Depends(deps.provide_dagmanager),
        world_client: Optional[WorldServiceClient] = Depends(
            deps.provide_world_client_optional
        ),
        degradation: DegradationManager = Depends(deps.provide_degradation),
        enforce_live_guard: bool = Depends(deps.provide_enforce_live_guard),
        rebalance_schema_version: int = Depends(deps.provide_rebalance_schema_version),
        alpha_metrics_capable: bool = Depends(deps.provide_alpha_metrics_capable),
    ) -> dict[str, Any]:
        redis_conn = _resolve_dependency(redis_conn, deps.provide_redis_conn)
        database_obj = _resolve_dependency(database_obj, deps.provide_database)
        dagmanager = _resolve_dependency(dagmanager, deps.provide_dagmanager)
        world_client = _resolve_dependency(
            world_client, deps.provide_world_client_optional
        )
        degradation = _resolve_dependency(degradation, deps.provide_degradation)
        enforce_live_guard = _resolve_dependency(
            enforce_live_guard, deps.provide_enforce_live_guard
        )
        health_data = await gateway_health(
            redis_conn,
            database_obj,
            dagmanager,
            world_client,
            rebalance_schema_version=rebalance_schema_version,
            alpha_metrics_capable=alpha_metrics_capable,
        )
        health_data["degrade_level"] = degradation.level.name
        health_data["enforce_live_guard"] = enforce_live_guard
        try:
            health_data["pretrade"] = gw_metrics.get_pretrade_stats()
        except Exception:
            pass
        return health_data

    @router.get("/health")
    async def health(
        redis_conn: Any = Depends(deps.provide_redis_conn),
        database_obj: Any = Depends(deps.provide_database),
        dagmanager: DagManagerClient = Depends(deps.provide_dagmanager),
        world_client: Optional[WorldServiceClient] = Depends(
            deps.provide_world_client_optional
        ),
        rebalance_schema_version: int = Depends(deps.provide_rebalance_schema_version),
        alpha_metrics_capable: bool = Depends(deps.provide_alpha_metrics_capable),
    ) -> dict[str, Any]:
        redis_conn = _resolve_dependency(redis_conn, deps.provide_redis_conn)
        database_obj = _resolve_dependency(database_obj, deps.provide_database)
        dagmanager = _resolve_dependency(dagmanager, deps.provide_dagmanager)
        world_client = _resolve_dependency(
            world_client, deps.provide_world_client_optional
        )
        return await gateway_health(
            redis_conn,
            database_obj,
            dagmanager,
            world_client,
            rebalance_schema_version=rebalance_schema_version,
            alpha_metrics_capable=alpha_metrics_capable,
        )

    return router


__all__ = ["create_router"]
