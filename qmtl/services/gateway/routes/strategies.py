from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, status

from qmtl.services.gateway import metrics as gw_metrics
from qmtl.services.gateway.dagmanager_client import DagManagerClient
from qmtl.services.gateway.models import (
    QueuesByTagResponse,
    StatusResponse,
    StrategyAck,
    StrategySubmit,
)
from qmtl.services.gateway.strategy_manager import StrategyManager
from qmtl.services.gateway.strategy_submission import StrategySubmissionConfig, StrategySubmissionHelper

from .dependencies import GatewayDependencyProvider


def create_router(deps: GatewayDependencyProvider) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/strategies",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=StrategyAck,
    )
    async def post_strategies(
        payload: StrategySubmit,
        submission_helper: StrategySubmissionHelper = Depends(
            deps.provide_submission_helper
        ),
    ) -> StrategyAck:
        start = time.perf_counter()
        result = await submission_helper.process(
            payload,
            StrategySubmissionConfig(
                submit=True,
                diff_timeout=0.1,
            ),
        )
        resp = StrategyAck(
            strategy_id=result.strategy_id,
            queue_map=result.queue_map,
            sentinel_id=result.sentinel_id,
            node_ids_crc32=result.node_ids_crc32,
            downgraded=result.downgraded,
            downgrade_reason=result.downgrade_reason,
            safe_mode=result.safe_mode,
        )
        duration_ms = (time.perf_counter() - start) * 1000
        gw_metrics.observe_gateway_latency(duration_ms)
        return resp

    @router.post(
        "/strategies/dry-run",
        status_code=status.HTTP_200_OK,
        response_model=StrategyAck,
    )
    async def post_strategies_dry_run(
        payload: StrategySubmit,
        submission_helper: StrategySubmissionHelper = Depends(
            deps.provide_submission_helper
        ),
    ) -> StrategyAck:
        result = await submission_helper.process(
            payload,
            StrategySubmissionConfig(
                submit=False,
                strategy_id="dryrun",
                diff_timeout=0.5,
                prefer_diff_queue_map=True,
                sentinel_default="",
                diff_strategy_id="dryrun",
                use_crc_sentinel_fallback=True,
            ),
        )
        return StrategyAck(
            strategy_id=result.strategy_id,
            queue_map=result.queue_map,
            sentinel_id=result.sentinel_id,
            node_ids_crc32=result.node_ids_crc32,
            downgraded=result.downgraded,
            downgrade_reason=result.downgrade_reason,
            safe_mode=result.safe_mode,
        )

    @router.get(
        "/strategies/{strategy_id}/status", response_model=StatusResponse
    )
    async def get_status(
        strategy_id: str,
        manager: StrategyManager = Depends(deps.provide_manager),
    ) -> StatusResponse:
        status_value = await manager.status(strategy_id)
        if status_value is None:
            raise HTTPException(status_code=404, detail="strategy not found")
        return StatusResponse(status=status_value)

    @router.get("/queues/by_tag", response_model=QueuesByTagResponse)
    async def queues_by_tag(
        tags: str,
        interval: int,
        match_mode: str | None = None,
        world_id: str = "",
        dagmanager: DagManagerClient = Depends(deps.provide_dagmanager),
    ) -> QueuesByTagResponse:
        from qmtl.foundation.common.tagquery import split_tags, normalize_match_mode

        tag_list = split_tags(tags)
        mode = normalize_match_mode(match_mode).value
        queues = await dagmanager.get_queues_by_tag(
            tag_list, interval, mode, world_id or None
        )
        return {"queues": queues}

    return router


__all__ = ["create_router"]
