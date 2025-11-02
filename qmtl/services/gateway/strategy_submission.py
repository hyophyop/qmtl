from __future__ import annotations

import json
from dataclasses import dataclass
import logging
from http import HTTPStatus
from typing import Any

from fastapi import HTTPException
from httpx import HTTPStatusError
from . import metrics as gw_metrics
from .models import StrategySubmit
from .submission import SubmissionPipeline, StrategyComputeContext
from .world_client import WorldServiceClient


logger = logging.getLogger(__name__)


@dataclass
class StrategySubmissionConfig:
    """Behavior flags for the shared strategy submission helper."""

    submit: bool
    strategy_id: str | None = None
    diff_timeout: float = 0.1
    prefer_diff_queue_map: bool = False
    sentinel_default: str | None = None
    diff_strategy_id: str | None = None
    use_crc_sentinel_fallback: bool = False


@dataclass
class StrategySubmissionResult:
    """Structured result returned by the helper."""

    strategy_id: str
    queue_map: dict[str, list[dict[str, Any] | Any]]
    sentinel_id: str
    node_ids_crc32: int
    downgraded: bool = False
    downgrade_reason: "DowngradeReason | str | None" = None
    safe_mode: bool = False


class StrategySubmissionHelper:
    """Normalize DAG processing for ingestion and dry-run endpoints."""

    def __init__(
        self,
        manager,
        dagmanager,
        database,
        *,
        pipeline: SubmissionPipeline | None = None,
        world_client: WorldServiceClient | None = None,
    ) -> None:
        self._manager = manager
        self._dagmanager = dagmanager
        self._database = database
        self._pipeline = pipeline or SubmissionPipeline(dagmanager)
        self._world_client = world_client

    async def process(
        self, payload: StrategySubmit, config: StrategySubmissionConfig
    ) -> StrategySubmissionResult:
        prepared = await self._pipeline.prepare(payload)
        dag = prepared.dag
        node_crc32 = prepared.node_ids_crc32
        strategy_ctx = prepared.compute_context
        worlds = prepared.worlds
        downgraded = strategy_ctx.downgraded
        downgrade_reason = strategy_ctx.downgrade_reason
        safe_mode = strategy_ctx.safe_mode

        # Emit a downgrade metric whenever we enter safe mode due to missing context.
        if downgraded and downgrade_reason:
            reason = getattr(downgrade_reason, "value", downgrade_reason)
            gw_metrics.strategy_compute_context_downgrade_total.labels(
                reason=reason
            ).inc()

        strategy_id, existed = await self._maybe_submit(
            payload, config, downgraded, strategy_ctx
        )
        if existed:
            raise HTTPException(
                status_code=409,
                detail={"code": "E_DUPLICATE", "strategy_id": strategy_id},
            )

        if config.submit and self._database is not None:
            await self._persist_world_bindings(worlds, payload.world_id, strategy_id)

        queue_map = {}
        exec_domain = strategy_ctx.execution_domain or None

        prefer_diff = config.prefer_diff_queue_map
        diff_strategy_id = config.diff_strategy_id or strategy_id
        dag_json = json.dumps(dag)

        sentinel_default = (
            config.sentinel_default
            if config.sentinel_default is not None
            else (f"{strategy_id}-sentinel" if strategy_id else "")
        )

        sentinel_id = sentinel_default
        diff_queue_map: dict[str, list[dict[str, Any]]] | None = None
        diff_error = False
        try:
            sentinel_id, diff_queue_map = await self._pipeline.run_diff(
                strategy_id=diff_strategy_id,
                dag_json=dag_json,
                worlds=worlds,
                fallback_world_id=payload.world_id,
                compute_ctx=strategy_ctx,
                timeout=config.diff_timeout,
                prefer_queue_map=prefer_diff,
                expected_crc32=node_crc32,
            )
            if not sentinel_id:
                sentinel_id = sentinel_default
        except Exception:
            diff_error = True
            sentinel_id = sentinel_default
            diff_queue_map = None

        if prefer_diff and not diff_error and diff_queue_map is not None:
            queue_map = diff_queue_map
        else:
            queue_map = await self._pipeline.build_queue_map(
                dag, worlds, payload.world_id, exec_domain
            )
            if (
                prefer_diff
                and diff_error
                and not sentinel_id
                and config.use_crc_sentinel_fallback
            ):
                sentinel_id = self._crc_sentinel(dag)

        if not prefer_diff and config.use_crc_sentinel_fallback and not sentinel_id:
            sentinel_id = self._crc_sentinel(dag)

        return StrategySubmissionResult(
            strategy_id=strategy_id,
            queue_map=queue_map,
            sentinel_id=sentinel_id,
            node_ids_crc32=node_crc32,
            downgraded=downgraded,
            downgrade_reason=downgrade_reason,
            safe_mode=safe_mode,
        )

    async def _maybe_submit(
        self,
        payload: StrategySubmit,
        config: StrategySubmissionConfig,
        downgraded: bool,
        strategy_ctx: StrategyComputeContext,
    ) -> tuple[str, bool]:
        if config.submit:
            if self._manager is None:
                raise RuntimeError("StrategyManager is required for submission")
            return await self._manager.submit(
                payload,
                skip_downgrade_metric=downgraded,
                strategy_context=strategy_ctx,
            )
        strategy_id = config.strategy_id or "dryrun"
        return strategy_id, False

    def _crc_sentinel(self, dag: dict[str, Any]) -> str:
        from qmtl.foundation.common import crc32_of_list

        crc = crc32_of_list(n.get("node_id", "") for n in dag.get("nodes", []))
        return f"dryrun:{crc:08x}"

    async def _persist_world_bindings(
        self, worlds: list[str], default_world: str | None, strategy_id: str
    ) -> None:
        if self._database is None:
            return
        targets = worlds or ([default_world] if default_world else [])
        for world_id in targets:
            if not world_id:
                continue
            try:
                await self._database.upsert_wsb(world_id, strategy_id)
            except Exception:
                logger.exception(
                    "Failed to upsert world binding", extra={"world_id": world_id}
                )
                continue

            if self._world_client is None:
                continue

            try:
                await self._world_client.post_bindings(
                    world_id, {"strategies": [strategy_id]}
                )
            except HTTPStatusError as exc:
                status_code = exc.response.status_code if exc.response else None
                if status_code == HTTPStatus.CONFLICT:
                    continue
                logger.warning(
                    "WorldService binding sync failed for %s (status=%s)",
                    world_id,
                    status_code,
                    exc_info=exc,
                )
            except Exception as exc:  # pragma: no cover - defensive network guard
                logger.warning(
                    "WorldService binding sync failed for %s", world_id, exc_info=exc
                )

    async def _build_queue_map_from_queries(
        self,
        dag: dict[str, Any],
        worlds: list[str],
        default_world: str | None,
        execution_domain: str | None,
    ) -> dict[str, list[dict[str, Any] | Any]]:
        return await self._pipeline.build_queue_map(
            dag, worlds, default_world, execution_domain
        )
