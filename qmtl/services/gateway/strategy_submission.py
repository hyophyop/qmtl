from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from http import HTTPStatus
from typing import Any, Awaitable, cast

from fastapi import HTTPException
from httpx import HTTPStatusError

from qmtl.foundation.common.compute_context import DowngradeReason
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
    downgrade_reason: DowngradeReason | str | None = None
    safe_mode: bool = False
    queue_map_source: str | None = None
    diff_error: bool = False
    crc_fallback: bool = False


@dataclass
class DiffOutcome:
    sentinel_id: str | None
    queue_map: dict[str, list[dict[str, Any] | Any]] | None
    error: bool


@dataclass
class QueueResolution:
    """Represents queue-map resolution across diff and fallback paths."""

    sentinel_id: str
    queue_map: dict[str, list[dict[str, Any] | Any]]
    source: str
    diff_error: bool = False
    crc_fallback: bool = False


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
        default_world = worlds[0] if worlds else None
        downgraded = strategy_ctx.downgraded
        downgrade_reason = strategy_ctx.downgrade_reason
        safe_mode = strategy_ctx.safe_mode

        self._record_downgrade_metric(downgraded, downgrade_reason)

        strategy_id, existed = await self._maybe_submit(
            payload, config, downgraded, strategy_ctx
        )
        if existed:
            raise HTTPException(
                status_code=409,
                detail={"code": "E_DUPLICATE", "strategy_id": strategy_id},
            )

        if config.submit and self._database is not None:
            await self._persist_world_bindings(worlds, default_world, strategy_id)

        resolution = await self._build_queue_outputs(
            dag,
            worlds,
            payload,
            strategy_ctx,
            config,
            node_crc32,
            strategy_id,
            default_world,
        )

        return StrategySubmissionResult(
            strategy_id=strategy_id,
            queue_map=resolution.queue_map,
            sentinel_id=resolution.sentinel_id,
            node_ids_crc32=node_crc32,
            downgraded=downgraded,
            downgrade_reason=downgrade_reason,
            safe_mode=safe_mode,
            queue_map_source=resolution.source,
            diff_error=resolution.diff_error,
            crc_fallback=resolution.crc_fallback,
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
            return cast(
                tuple[str, bool],
                await self._manager.submit(
                    payload,
                    skip_downgrade_metric=downgraded,
                    strategy_context=strategy_ctx,
                ),
            )
        strategy_id = config.strategy_id or "dryrun"
        return strategy_id, False

    def _crc_sentinel(self, dag: dict[str, Any]) -> str:
        from qmtl.foundation.common import crc32_of_list

        crc = crc32_of_list(n.get("node_id", "") for n in dag.get("nodes", []))
        return f"dryrun:{crc:08x}"

    def _record_downgrade_metric(
        self, downgraded: bool, downgrade_reason: DowngradeReason | str | None
    ) -> None:
        if not downgraded or not downgrade_reason:
            return
        reason = getattr(downgrade_reason, "value", downgrade_reason)
        gw_metrics.strategy_compute_context_downgrade_total.labels(
            reason=reason
        ).inc()

    async def _build_queue_outputs(
        self,
        dag: dict[str, Any],
        worlds: list[str],
        payload: StrategySubmit,
        strategy_ctx: StrategyComputeContext,
        config: StrategySubmissionConfig,
        node_crc32: int,
        strategy_id: str,
        default_world: str | None,
    ) -> QueueResolution:
        exec_domain = strategy_ctx.execution_domain or None
        diff_outcome = await self._compute_diff_outcome(
            dag,
            worlds,
            payload,
            strategy_ctx,
            config,
            node_crc32,
            strategy_id,
            default_world,
        )

        resolution = await self._resolve_queue_map(
            dag,
            worlds,
            payload,
            exec_domain,
            config,
            diff_outcome,
            default_world,
        )

        sentinel = resolution.sentinel_id or self._sentinel_default(
            config, strategy_id
        )
        return QueueResolution(
            sentinel_id=sentinel,
            queue_map=resolution.queue_map,
            source=resolution.source,
            diff_error=resolution.diff_error,
            crc_fallback=resolution.crc_fallback,
        )

    async def _compute_diff_outcome(
        self,
        dag: dict[str, Any],
        worlds: list[str],
        payload: StrategySubmit,
        strategy_ctx: StrategyComputeContext,
        config: StrategySubmissionConfig,
        node_crc32: int,
        strategy_id: str,
        default_world: str | None,
    ) -> DiffOutcome:
        diff_strategy_id = config.diff_strategy_id or strategy_id
        return await self._run_diff(
            config.prefer_diff_queue_map,
            diff_strategy_id,
            dag,
            worlds,
            payload,
            strategy_ctx,
            config,
            node_crc32,
            default_world,
        )

    async def _resolve_queue_map(
        self,
        dag: dict[str, Any],
        worlds: list[str],
        payload: StrategySubmit,
        exec_domain: str | None,
        config: StrategySubmissionConfig,
        diff_outcome: DiffOutcome,
        default_world: str | None,
    ) -> QueueResolution:
        diff_sentinel = diff_outcome.sentinel_id or ""
        prefer_diff = config.prefer_diff_queue_map
        if self._use_diff_queue_map(prefer_diff, diff_outcome):
            queue_map = cast(
                dict[str, list[dict[str, Any] | Any]],
                diff_outcome.queue_map,
            )
            return QueueResolution(
                sentinel_id=diff_sentinel,
                queue_map=queue_map,
                source="diff",
            )

        queue_map = await self._pipeline.build_queue_map(
            dag, worlds, default_world, exec_domain
        )
        sentinel_id, crc_fallback = self._resolve_sentinel_id(
            dag=dag,
            diff_sentinel=diff_sentinel,
            prefer_diff=prefer_diff,
            diff_outcome=diff_outcome,
            config=config,
        )

        return QueueResolution(
            sentinel_id=sentinel_id,
            queue_map=queue_map,
            source="tag_query",
            diff_error=diff_outcome.error,
            crc_fallback=crc_fallback,
        )

    def _use_diff_queue_map(
        self, prefer_diff: bool, diff_outcome: DiffOutcome
    ) -> bool:
        return (
            prefer_diff
            and not diff_outcome.error
            and diff_outcome.queue_map is not None
        )

    def _resolve_sentinel_id(
        self,
        dag: dict[str, Any],
        diff_sentinel: str,
        prefer_diff: bool,
        diff_outcome: DiffOutcome,
        config: StrategySubmissionConfig,
    ) -> tuple[str, bool]:
        sentinel_id = diff_sentinel
        crc_fallback = self._should_crc_fallback(
            prefer_diff=prefer_diff,
            diff_outcome=diff_outcome,
            sentinel_id=sentinel_id,
            config=config,
        )
        if crc_fallback:
            sentinel_id = self._crc_sentinel(dag)
        return sentinel_id, crc_fallback

    def _should_crc_fallback(
        self,
        prefer_diff: bool,
        diff_outcome: DiffOutcome,
        sentinel_id: str,
        config: StrategySubmissionConfig,
    ) -> bool:
        if sentinel_id:
            return False
        if not config.use_crc_sentinel_fallback:
            return False
        if prefer_diff:
            return diff_outcome.error
        return True

    def _sentinel_default(
        self, config: StrategySubmissionConfig, strategy_id: str
    ) -> str:
        if config.sentinel_default is not None:
            return config.sentinel_default
        return f"{strategy_id}-sentinel" if strategy_id else ""

    async def _run_diff(
        self,
        prefer_diff: bool,
        diff_strategy_id: str,
        dag: dict[str, Any],
        worlds: list[str],
        payload: StrategySubmit,
        strategy_ctx: StrategyComputeContext,
        config: StrategySubmissionConfig,
        node_crc32: int,
        default_world: str | None,
    ) -> DiffOutcome:
        dag_json = json.dumps(dag)
        try:
            outcome = await self._pipeline.run_diff(
                strategy_id=diff_strategy_id,
                dag_json=dag_json,
                worlds=worlds,
                fallback_world_id=default_world,
                compute_ctx=strategy_ctx,
                timeout=config.diff_timeout,
                prefer_queue_map=prefer_diff,
                expected_crc32=node_crc32,
            )
            return DiffOutcome(
                sentinel_id=outcome.sentinel_id,
                queue_map=outcome.queue_map,
                error=False,
            )
        except Exception:
            return DiffOutcome(sentinel_id=None, queue_map=None, error=True)

    async def _persist_world_bindings(
        self, worlds: list[str], default_world: str | None, strategy_id: str
    ) -> None:
        if self._database is None:
            return
        for world_id in self._binding_targets(worlds, default_world):
            await self._persist_world_binding(world_id, strategy_id)

    def _binding_targets(
        self, worlds: list[str], default_world: str | None
    ) -> list[str]:
        if worlds:
            return [w for w in worlds if w]
        return [default_world] if default_world else []

    async def _persist_world_binding(self, world_id: str, strategy_id: str) -> None:
        try:
            await self._database.upsert_wsb(world_id, strategy_id)
        except Exception:
            logger.exception(
                "Failed to upsert world binding", extra={"world_id": world_id}
            )
            return

        await self._sync_world_binding(world_id, strategy_id)

    async def _sync_world_binding(self, world_id: str, strategy_id: str) -> None:
        if self._world_client is None:
            return

        try:
            await self._world_client.post_bindings(
                world_id, {"strategies": [strategy_id]}
            )
        except HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response else None
            if status_code == HTTPStatus.CONFLICT:
                return
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
