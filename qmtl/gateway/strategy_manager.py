from __future__ import annotations

import base64
import copy
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import redis.asyncio as redis
from fastapi import HTTPException
from opentelemetry import trace

from . import metrics as gw_metrics
from .compute_context import build_strategy_compute_context
from .commit_log import CommitLogWriter
from .database import Database
from .degradation import DegradationManager, DegradationLevel
from .fsm import StrategyFSM
from .models import StrategySubmit
from .strategy_persistence import StrategyQueue, StrategyStorage

tracer = trace.get_tracer(__name__)


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

    def __post_init__(self) -> None:
        if self.storage is None:
            self.storage = StrategyStorage(self.redis)
        if self.queue is None:
            self.queue = StrategyQueue(self.redis)

    async def submit(
        self,
        payload: StrategySubmit,
        *,
        skip_downgrade_metric: bool = False,
    ) -> tuple[str, bool]:
        with tracer.start_as_current_span("gateway.submit"):
            decoded = self._decode_dag(payload)

            (
                compute_ctx,
                context_mapping,
                world_list,
                downgraded,
                downgrade_reason,
            ) = self._build_compute_context(payload)

            if (
                downgraded
                and downgrade_reason
                and not skip_downgrade_metric
            ):
                gw_metrics.strategy_compute_context_downgrade_total.labels(
                    reason=downgrade_reason
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
                compute_ctx,
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
        compute_ctx: dict[str, str | bool | None],
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
        compute_ctx: dict[str, str | None],
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

    def _build_compute_context(
        self, payload: StrategySubmit
    ) -> tuple[
        dict[str, str | bool | None],
        dict[str, str],
        list[str],
        bool,
        str | None,
    ]:
        world_candidates: list[str] = []
        if payload.world_id:
            world_candidates.append(payload.world_id)
        wid_list = getattr(payload, "world_ids", None)
        if wid_list:
            for wid in wid_list:
                if wid:
                    world_candidates.append(wid)
        unique_worlds: list[str] = []
        seen: set[str] = set()
        for wid in world_candidates:
            normalised = self._ctx_value(wid)
            if not normalised:
                continue
            if normalised not in seen:
                seen.add(normalised)
                unique_worlds.append(normalised)
        meta = payload.meta if isinstance(payload.meta, dict) else None
        base_ctx, downgraded, downgrade_reason, safe_mode = build_strategy_compute_context(meta)
        compute_ctx: dict[str, str | bool | None] = dict(base_ctx)
        compute_ctx["world_id"] = unique_worlds[0] if unique_worlds else None
        if downgraded:
            compute_ctx["downgraded"] = True
            if downgrade_reason:
                compute_ctx["downgrade_reason"] = downgrade_reason
            if safe_mode:
                compute_ctx["safe_mode"] = True
        context_mapping: dict[str, str] = {
            f"compute_{k}": v
            for k, v in compute_ctx.items()
            if isinstance(v, str) and v
        }
        return compute_ctx, context_mapping, unique_worlds, downgraded, downgrade_reason
