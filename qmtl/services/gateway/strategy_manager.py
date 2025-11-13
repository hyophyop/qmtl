from __future__ import annotations

import base64
import copy
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import redis.asyncio as redis
from fastapi import HTTPException
from opentelemetry import trace

from . import metrics as gw_metrics
from .commit_log import CommitLogWriter
from .database import Database
from .degradation import DegradationManager
from .fsm import StrategyFSM
from .models import StrategySubmit
from .strategy_persistence import StrategyQueue, StrategyStorage
from .submission import ComputeContextService, StrategyComputeContext
from .world_client import WorldServiceClient

tracer = trace.get_tracer(__name__)
logger = logging.getLogger(__name__)


@dataclass
class DecodedDag:
    strategy_id: str
    dag: dict[str, Any]
    dag_for_storage: dict[str, Any]
    encoded_dag: str
    dag_hash: str


@dataclass
class StrategyManager:
    redis: redis.Redis
    database: Database
    fsm: StrategyFSM
    degrade: Optional[DegradationManager] = None
    insert_sentinel: bool = True
    commit_log_writer: CommitLogWriter | None = None
    storage: StrategyStorage | None = None
    queue: StrategyQueue | None = None
    context_service: ComputeContextService | None = None
    world_client: WorldServiceClient | None = None

    def __post_init__(self) -> None:
        if self.storage is None:
            self.storage = StrategyStorage(self.redis)
        if self.queue is None:
            self.queue = StrategyQueue(self.redis)
        if self.context_service is None:
            self.context_service = ComputeContextService()

    async def submit(
        self,
        payload: StrategySubmit,
        *,
        skip_downgrade_metric: bool = False,
        strategy_context: StrategyComputeContext | None = None,
    ) -> tuple[str, bool]:
        with tracer.start_as_current_span("gateway.submit"):
            decoded = self._decode_dag(payload)
            strategy_ctx = await self._resolve_strategy_context(
                payload, strategy_context
            )
            self._record_downgrade_metric(
                strategy_ctx.context, skip_downgrade_metric
            )

            strategy_id, existed = await self._register_strategy(decoded)
            if existed:
                return strategy_id, True

            await self._finalize_submission(
                strategy_id,
                decoded,
                payload,
                strategy_ctx,
            )
            return strategy_id, False

    async def status(self, strategy_id: str) -> Optional[str]:
        return await self.fsm.get(strategy_id)

    def _increment_lost_requests(self) -> None:
        gw_metrics.lost_requests_total.inc()
        try:
            gw_metrics.lost_requests_total._val = (
                gw_metrics.lost_requests_total._value.get()
            )  # type: ignore[attr-defined]
        except AttributeError:
            pass

    def _decode_dag(self, payload: StrategySubmit) -> DecodedDag:
        dag_dict, dag_for_storage, dag_hash = self._parse_dag_payload(payload)
        strategy_id = str(uuid.uuid4())
        dag_for_storage = self._inject_version_sentinel(
            strategy_id, dag_for_storage, payload.meta
        )
        encoded_dag = base64.b64encode(json.dumps(dag_for_storage).encode()).decode()
        return DecodedDag(
            strategy_id=strategy_id,
            dag=dag_dict,
            dag_for_storage=dag_for_storage,
            encoded_dag=encoded_dag,
            dag_hash=dag_hash,
        )

    def _parse_dag_payload(
        self, payload: StrategySubmit
    ) -> tuple[dict[str, Any], dict[str, Any], str]:
        try:
            dag_bytes = base64.b64decode(payload.dag_json)
            dag_dict = json.loads(dag_bytes.decode())
        except Exception:
            dag_dict = json.loads(payload.dag_json)

        dag_hash = hashlib.sha256(
            json.dumps(dag_dict, sort_keys=True).encode()
        ).hexdigest()
        return dag_dict, copy.deepcopy(dag_dict), dag_hash

    def _inject_version_sentinel(
        self,
        strategy_id: str,
        dag: dict[str, Any],
        meta: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not self.insert_sentinel:
            return dag

        version_meta: str | None = None
        if isinstance(meta, dict):
            for key in ("version", "strategy_version", "build_version"):
                val = meta.get(key)
                if isinstance(val, str):
                    candidate = val.strip()
                    if candidate:
                        version_meta = candidate
                        break

        sentinel = {
            "node_type": "VersionSentinel",
            "node_id": f"{strategy_id}-sentinel",
        }
        if version_meta:
            sentinel["version"] = version_meta

        dag.setdefault("nodes", []).append(sentinel)
        return dag

    async def _ensure_unique_strategy(
        self, strategy_id: str, dag_hash: str, encoded_dag: str
    ) -> tuple[str, bool]:
        if self.storage is None:
            raise RuntimeError("Strategy storage is not configured")
        return await self.storage.save_unique(strategy_id, dag_hash, encoded_dag)

    async def _publish_submission(
        self,
        strategy_id: str,
        dag_for_storage: dict[str, Any],
        encoded_dag: str,
        dag_hash: str,
        payload: StrategySubmit,
        compute_ctx: dict[str, Any],
        world_list: list[str],
    ) -> None:
        if self.commit_log_writer is None:
            return
        try:
            record = self._build_commit_log_payload(
                strategy_id,
                dag_for_storage,
                encoded_dag,
                dag_hash,
                payload,
                compute_ctx,
                world_list,
            )
            await self.commit_log_writer.publish_submission(strategy_id, record)
        except Exception as exc:
            self._increment_lost_requests()
            await self._rollback_submission(strategy_id, dag_hash)
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "E_COMMITLOG",
                    "message": "commit log unavailable",
                },
            ) from exc

    async def _enqueue_strategy(self, strategy_id: str) -> None:
        if self.queue is None:
            raise RuntimeError("Strategy queue is not configured")
        await self.queue.enqueue(strategy_id, self.degrade)

    async def _rollback_submission(self, strategy_id: str, dag_hash: str) -> None:
        if self.storage is None:
            return
        await self.storage.rollback(strategy_id, dag_hash)

    def _build_commit_log_payload(
        self,
        strategy_id: str,
        dag: dict[str, Any],
        encoded_dag: str,
        dag_hash: str,
        payload: StrategySubmit,
        compute_ctx: dict[str, Any],
        world_ids: list[str],
    ) -> dict[str, Any]:
        submitted_at = datetime.now(timezone.utc).isoformat()
        log_payload: dict[str, Any] = {
            "event": "gateway.ingest",
            "version": 1,
            "strategy_id": strategy_id,
            "dag_hash": dag_hash,
            "dag": dag,
            "dag_base64": encoded_dag,
            "node_ids_crc32": payload.node_ids_crc32,
            "insert_sentinel": bool(self.insert_sentinel),
            "compute_context": compute_ctx,
            "world_ids": world_ids,
            "submitted_at": submitted_at,
        }
        if payload.world_id:
            log_payload["world_id"] = self._ctx_value(payload.world_id)
        meta = payload.meta if isinstance(payload.meta, dict) else None
        if meta:
            log_payload["meta"] = self._json_safe(meta)
        return log_payload

    def _json_safe(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(k): self._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._json_safe(v) for v in value]
        return str(value)

    def _ctx_value(self, value: Any | None) -> str | None:
        if isinstance(value, bytes):
            value = value.decode()
        if value is None:
            return None
        if isinstance(value, (str, int, float)):
            text = str(value).strip()
            return text or None
        return None

    async def update_history_metadata(self, strategy_id: str, report: Any) -> None:
        storage_key = f"strategy:{strategy_id}"
        exists = await self.redis.exists(storage_key)
        if not exists:
            raise KeyError(strategy_id)

        artifact = getattr(report, "artifact", None)
        dataset_fp = getattr(report, "dataset_fingerprint", None)
        if dataset_fp is None and artifact is not None:
            dataset_fp = getattr(artifact, "dataset_fingerprint", None)
        as_of_value = getattr(report, "as_of", None)
        if as_of_value is None and artifact is not None:
            as_of_value = getattr(artifact, "as_of", None)

        mapping = self._build_history_mapping(report, dataset_fp, as_of_value)
        if mapping:
            await self.redis.hset(storage_key, mapping=mapping)

        meta_payload = self._build_meta_payload(
            report, artifact, dataset_fp, as_of_value
        )
        await self.redis.hset(
            storage_key,
            mapping={f"seamless:{report.node_id}": json.dumps(meta_payload)},
        )

        world_id = getattr(report, "world_id", None)
        if self.world_client is not None and world_id:
            try:
                world_payload = self._build_world_payload(
                    strategy_id, report, meta_payload
                )
                await self.world_client.post_history_metadata(
                    world_id=str(world_id),
                    payload=world_payload,
                )
            except Exception:
                logger.exception(
                    "failed to forward seamless metadata to worldservice",
                    extra={
                        "strategy_id": strategy_id,
                        "world_id": world_id,
                        "node_id": report.node_id,
                    },
                )

    def _build_history_mapping(
        self,
        report: Any,
        dataset_fp: Any,
        as_of_value: Any,
    ) -> dict[str, str]:
        mapping: dict[str, str] = {}
        world_id = getattr(report, "world_id", None)
        if world_id:
            mapping["compute_world_id"] = str(world_id)
        execution_domain = getattr(report, "execution_domain", None)
        if execution_domain:
            mapping["compute_execution_domain"] = str(execution_domain)
        if as_of_value:
            mapping["compute_as_of"] = str(as_of_value)
        if dataset_fp:
            mapping["compute_dataset_fingerprint"] = str(dataset_fp)
        return mapping

    def _build_meta_payload(
        self,
        report: Any,
        artifact: Any,
        dataset_fp: Any,
        as_of_value: Any,
    ) -> dict[str, Any]:
        world_id = getattr(report, "world_id", None)
        execution_domain = getattr(report, "execution_domain", None)
        coverage_bounds = getattr(report, "coverage_bounds", None)
        artifact_payload: Any | None = None
        if artifact is not None:
            model_dump = getattr(artifact, "model_dump", None)
            if callable(model_dump):
                artifact_payload = model_dump()
            else:
                artifact_payload = artifact.__dict__

        meta_payload: dict[str, Any] = {
            "node_id": report.node_id,
            "interval": int(report.interval),
            "rows": getattr(report, "rows", None),
            "coverage_bounds": list(coverage_bounds) if coverage_bounds else None,
            "conformance_flags": getattr(report, "conformance_flags", None) or {},
            "conformance_warnings": getattr(
                report, "conformance_warnings", None
            )
            or [],
            "artifact": artifact_payload,
            "dataset_fingerprint": dataset_fp,
            "as_of": as_of_value,
            "updated_at": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
        }
        if world_id:
            meta_payload["world_id"] = str(world_id)
        if execution_domain:
            meta_payload["execution_domain"] = str(execution_domain)
        return meta_payload

    def _build_world_payload(
        self,
        strategy_id: str,
        report: Any,
        meta_payload: dict[str, Any],
    ) -> dict[str, Any]:
        payload = dict(meta_payload)
        payload["strategy_id"] = strategy_id
        world_id = getattr(report, "world_id", None)
        if world_id:
            payload["world_id"] = str(world_id)
        return payload

    async def _build_compute_context(
        self, payload: StrategySubmit
    ) -> StrategyComputeContext:
        if self.context_service is None:
            self.context_service = ComputeContextService()
        return await self.context_service.build(payload)

    async def _resolve_strategy_context(
        self,
        payload: StrategySubmit,
        strategy_context: StrategyComputeContext | None,
    ) -> StrategyComputeContext:
        if strategy_context is not None:
            return strategy_context
        return await self._build_compute_context(payload)

    def _record_downgrade_metric(
        self, compute_ctx: StrategyComputeContext, skip_downgrade_metric: bool
    ) -> None:
        if (
            skip_downgrade_metric
            or not compute_ctx.downgraded
            or not compute_ctx.downgrade_reason
        ):
            return
        reason = getattr(
            compute_ctx.downgrade_reason,
            "value",
            compute_ctx.downgrade_reason,
        )
        gw_metrics.strategy_compute_context_downgrade_total.labels(
            reason=reason
        ).inc()

    async def _register_strategy(
        self, decoded: DecodedDag
    ) -> tuple[str, bool]:
        try:
            return await self._ensure_unique_strategy(
                decoded.strategy_id,
                decoded.dag_hash,
                decoded.encoded_dag,
            )
        except Exception:
            self._increment_lost_requests()
            raise

    async def _finalize_submission(
        self,
        strategy_id: str,
        decoded: DecodedDag,
        payload: StrategySubmit,
        strategy_ctx: StrategyComputeContext,
    ) -> None:
        compute_ctx_payload = strategy_ctx.commit_log_payload()
        world_list = strategy_ctx.worlds_list()
        await self._publish_submission(
            strategy_id,
            decoded.dag_for_storage,
            decoded.encoded_dag,
            decoded.dag_hash,
            payload,
            compute_ctx_payload,
            world_list,
        )

        await self._enqueue_with_rollback(strategy_id, decoded.dag_hash)
        await self._persist_context(strategy_id, strategy_ctx)
        await self.fsm.create(strategy_id, payload.meta)

    async def _enqueue_with_rollback(
        self, strategy_id: str, dag_hash: str
    ) -> None:
        try:
            await self._enqueue_strategy(strategy_id)
        except Exception:
            self._increment_lost_requests()
            await self._rollback_submission(strategy_id, dag_hash)
            raise

    async def _persist_context(
        self, strategy_id: str, strategy_ctx: StrategyComputeContext
    ) -> None:
        context_mapping = strategy_ctx.redis_mapping()
        if not context_mapping:
            return
        await self.redis.hset(
            f"strategy:{strategy_id}", mapping=context_mapping
        )
