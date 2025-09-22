from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from . import metrics as gw_metrics
from .models import StrategySubmit
from .submission import SubmissionPipeline


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
    downgraded: bool = False
    downgrade_reason: str | None = None
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
    ) -> None:
        self._manager = manager
        self._dagmanager = dagmanager
        self._database = database
        self._pipeline = pipeline or SubmissionPipeline(dagmanager)

    async def process(
        self, payload: StrategySubmit, config: StrategySubmissionConfig
    ) -> StrategySubmissionResult:
        prepared = self._pipeline.prepare(payload)
        dag = prepared.dag
        compute_ctx = prepared.compute_context
        worlds = prepared.worlds
        downgraded = compute_ctx.downgraded
        downgrade_reason = compute_ctx.downgrade_reason
        safe_mode = compute_ctx.safe_mode

        # Emit a downgrade metric whenever we enter safe mode due to missing context.
        if downgraded and downgrade_reason:
            gw_metrics.strategy_compute_context_downgrade_total.labels(
                reason=downgrade_reason
            ).inc()

        strategy_id, existed = await self._maybe_submit(
            payload, config, downgraded
        )
        if existed:
            raise HTTPException(
                status_code=409,
                detail={"code": "E_DUPLICATE", "strategy_id": strategy_id},
            )

        if config.submit and self._database is not None:
            await self._persist_world_bindings(worlds, payload.world_id, strategy_id)

        queue_map = {}
        exec_domain = compute_ctx.execution_domain or None

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
                compute_ctx=compute_ctx,
                timeout=config.diff_timeout,
                prefer_queue_map=prefer_diff,
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
            downgraded=downgraded,
            downgrade_reason=downgrade_reason,
            safe_mode=safe_mode,
        )

    async def _maybe_submit(
        self,
        payload: StrategySubmit,
        config: StrategySubmissionConfig,
        downgraded: bool,
    ) -> tuple[str, bool]:
        if config.submit:
            if self._manager is None:
                raise RuntimeError("StrategyManager is required for submission")
            return await self._manager.submit(
                payload, skip_downgrade_metric=downgraded
            )
        strategy_id = config.strategy_id or "dryrun"
        return strategy_id, False

    def _validate_node_ids(self, dag: dict[str, Any], node_ids_crc32: int) -> None:
        from qmtl.common import crc32_of_list, compute_node_id

        nodes = dag.get("nodes", [])
        node_ids_for_crc: list[str] = []
        missing_fields: list[dict[str, Any]] = []
        mismatches: list[dict[str, str | int]] = []

        for idx, node in enumerate(nodes):
            nid = node.get("node_id")
            if not isinstance(nid, str) or not nid:
                node_ids_for_crc.append(str(nid or ""))
                missing_fields.append({"index": idx, "missing": ["node_id"]})
                continue

            node_ids_for_crc.append(nid)
            required = {
                "node_type": node.get("node_type"),
                "code_hash": node.get("code_hash"),
                "config_hash": node.get("config_hash"),
                "schema_hash": node.get("schema_hash"),
                "schema_compat_id": node.get("schema_compat_id"),
            }
            missing = [field for field, value in required.items() if not value]
            if missing:
                missing_fields.append(
                    {"index": idx, "node_id": nid, "missing": missing}
                )
                continue

            expected = compute_node_id(node)
            if nid != expected:
                mismatches.append({"index": idx, "node_id": nid, "expected": expected})

        crc = crc32_of_list(node_ids_for_crc)
        if missing_fields:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "E_NODE_ID_FIELDS",
                    "message": "node_id validation requires node_type, code_hash, config_hash, schema_hash and schema_compat_id",
                    "missing_fields": missing_fields,
                    "hint": "Regenerate the DAG with an updated SDK so each node includes the hashes required by compute_node_id().",
                },
            )

        if crc != node_ids_crc32:
            raise HTTPException(
                status_code=400,
                detail={"code": "E_CHECKSUM_MISMATCH", "message": "node id checksum mismatch"},
            )

        if mismatches:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "E_NODE_ID_MISMATCH",
                    "message": "node_id does not match canonical compute_node_id output",
                    "node_id_mismatch": mismatches,
                    "hint": "Ensure legacy world-coupled or pre-BLAKE3 node_ids are regenerated using compute_node_id().",
                },
            )

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
                pass

    def _crc_sentinel(self, dag: dict[str, Any]) -> str:
        from qmtl.common import crc32_of_list

        crc = crc32_of_list(n.get("node_id", "") for n in dag.get("nodes", []))
        return f"dryrun:{crc:08x}"
