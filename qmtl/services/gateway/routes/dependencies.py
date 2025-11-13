from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException, status

from qmtl.services.gateway.dagmanager_client import DagManagerClient
from qmtl.services.gateway.degradation import DegradationManager
from qmtl.services.gateway.strategy_manager import StrategyManager
from qmtl.services.gateway.strategy_submission import StrategySubmissionHelper
from qmtl.services.gateway.submission import ComputeContextService, SubmissionPipeline
from qmtl.services.gateway.ws import WebSocketHub
from qmtl.services.gateway.world_client import WorldServiceClient


class GatewayDependencyProvider:
    """Container that exposes FastAPI dependency callables for gateway routes."""

    def __init__(
        self,
        *,
        manager: StrategyManager,
        redis_conn: Any,
        database_obj: Any,
        dagmanager: DagManagerClient,
        ws_hub: Optional[WebSocketHub],
        degradation: DegradationManager,
        world_client: Optional[WorldServiceClient],
        enforce_live_guard: bool,
        rebalance_schema_version: int,
        alpha_metrics_capable: bool,
        fill_producer: Any | None = None,
        submission_pipeline: SubmissionPipeline | None = None,
    ) -> None:
        self._manager = manager
        self._redis_conn = redis_conn
        self._database_obj = database_obj
        self._dagmanager = dagmanager
        self._ws_hub = ws_hub
        self._degradation = degradation
        self._world_client = world_client
        self._enforce_live_guard = enforce_live_guard
        self._rebalance_schema_version = rebalance_schema_version
        self._alpha_metrics_capable = alpha_metrics_capable
        self._fill_producer = fill_producer
        if submission_pipeline is not None:
            self._pipeline = submission_pipeline
        else:
            context_service = ComputeContextService(world_client)
            self._pipeline = SubmissionPipeline(
                dagmanager,
                context_service=context_service,
            )
        self._submission_helper = StrategySubmissionHelper(
            manager,
            dagmanager,
            database_obj,
            pipeline=self._pipeline,
            world_client=self._world_client,
        )

    # Core dependencies -------------------------------------------------

    def provide_manager(self) -> StrategyManager:
        return self._manager

    def provide_redis_conn(self) -> Any:
        return self._redis_conn

    def provide_database(self) -> Any:
        return self._database_obj

    def provide_dagmanager(self) -> DagManagerClient:
        return self._dagmanager

    def provide_ws_hub(self) -> Optional[WebSocketHub]:
        return self._ws_hub

    def provide_degradation(self) -> DegradationManager:
        return self._degradation

    def provide_world_client_optional(self) -> Optional[WorldServiceClient]:
        return self._world_client

    def provide_world_client(self) -> WorldServiceClient:
        if self._world_client is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="WorldService disabled")
        return self._world_client

    def provide_submission_helper(self) -> StrategySubmissionHelper:
        return self._submission_helper

    def provide_submission_pipeline(self) -> SubmissionPipeline:
        return self._pipeline

    def provide_fill_producer(self) -> Any | None:
        return self._fill_producer

    def provide_enforce_live_guard(self) -> bool:
        return self._enforce_live_guard

    def provide_rebalance_schema_version(self) -> int:
        return self._rebalance_schema_version

    def provide_alpha_metrics_capable(self) -> bool:
        return self._alpha_metrics_capable


__all__ = ["GatewayDependencyProvider"]
