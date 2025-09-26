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
from .degradation import DegradationManager, DegradationLevel
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

            strategy_ctx = strategy_context or await self._build_compute_context(payload)
            compute_ctx = strategy_ctx.context
            compute_ctx_payload = strategy_ctx.commit_log_payload()
            context_mapping = strategy_ctx.redis_mapping()
            world_list = strategy_ctx.worlds_list()

            if (
                compute_ctx.downgraded
                and compute_ctx.downgrade_reason
                and not skip_downgrade_metric
            ):
                reason = getattr(
                    compute_ctx.downgrade_reason,
                    "value",
                    compute_ctx.downgrade_reason,
                )
                gw_metrics.strategy_compute_context_downgrade_total.labels(
                    reason=reason
                ).inc()

            try:
                strategy_id, existed = await self._ensure_unique_strategy(
                    decoded.strategy_id,
                    decoded.dag_hash,
                    decoded.encoded_dag,
                )
            except Exception:
                self._increment_lost_requests()
                raise

            if existed:
                return strategy_id, True

            await self._publish_submission(
                strategy_id,
                decoded.dag_for_storage,
                decoded.encoded_dag,
                decoded.dag_hash,
                payload,
                compute_ctx_payload,
                world_list,
            )

            try:
                await self._enqueue_strategy(strategy_id)
            except Exception:
                self._increment_lost_requests()
                await self._rollback_submission(strategy_id, decoded.dag_hash)
                raise

            if context_mapping:
                await self.redis.hset(
                    f"strategy:{strategy_id}", mapping=context_mapping
                )
            await self.fsm.create(strategy_id, payload.meta)
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
        try:
            dag_bytes = base64.b64decode(payload.dag_json)
            dag_dict = json.loads(dag_bytes.decode())
        except Exception:
            dag_dict = json.loads(payload.dag_json)

        dag_hash = hashlib.sha256(
            json.dumps(dag_dict, sort_keys=True).encode()
        ).hexdigest()
        strategy_id = str(uuid.uuid4())
        dag_for_storage = copy.deepcopy(dag_dict)
        if self.insert_sentinel:
            version_meta = None
            if isinstance(payload.meta, dict):
                for key in ("version", "strategy_version", "build_version"):
                    val = payload.meta.get(key)
                    if isinstance(val, str) and val.strip():
                        version_meta = val.strip()
                        break
            sentinel = {
                "node_type": "VersionSentinel",
                "node_id": f"{strategy_id}-sentinel",
            }
            if version_meta:
                sentinel["version"] = version_meta
            dag_for_storage.setdefault("nodes", []).append(sentinel)
        encoded_dag = base64.b64encode(json.dumps(dag_for_storage).encode()).decode()
        return DecodedDag(
            strategy_id=strategy_id,
            dag=dag_dict,
            dag_for_storage=dag_for_storage,
            encoded_dag=encoded_dag,
            dag_hash=dag_hash,
        )

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
        if mapping:
            await self.redis.hset(storage_key, mapping=mapping)

        meta_payload = {
            "node_id": report.node_id,
            "interval": int(report.interval),
            "rows": getattr(report, "rows", None),
            "coverage_bounds": list(report.coverage_bounds) if report.coverage_bounds else None,
            "conformance_flags": report.conformance_flags or {},
            "conformance_warnings": report.conformance_warnings or [],
            "artifact": artifact.model_dump() if getattr(artifact, "model_dump", None) else (artifact.__dict__ if artifact else None),
            "dataset_fingerprint": dataset_fp,
            "as_of": as_of_value,
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        if world_id:
            meta_payload["world_id"] = str(world_id)
        if execution_domain:
            meta_payload["execution_domain"] = str(execution_domain)
        await self.redis.hset(
            storage_key,
            mapping={f"seamless:{report.node_id}": json.dumps(meta_payload)},
        )

        if self.world_client is not None and world_id:
            try:
                world_payload = dict(meta_payload)
                world_payload["strategy_id"] = strategy_id
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

    async def _build_compute_context(
        self, payload: StrategySubmit
    ) -> StrategyComputeContext:
        if self.context_service is None:
            self.context_service = ComputeContextService()
        return await self.context_service.build(payload)
