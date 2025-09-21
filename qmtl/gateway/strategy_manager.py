from __future__ import annotations

import base64
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
from .commit_log import CommitLogWriter
from .database import Database
from .degradation import DegradationManager, DegradationLevel
from .fsm import StrategyFSM
from .models import StrategySubmit

tracer = trace.get_tracer(__name__)


@dataclass
class StrategyManager:
    redis: redis.Redis
    database: Database
    fsm: StrategyFSM
    degrade: Optional[DegradationManager] = None
    insert_sentinel: bool = True
    commit_log_writer: CommitLogWriter | None = None

    async def submit(self, payload: StrategySubmit) -> tuple[str, bool]:
        with tracer.start_as_current_span("gateway.submit"):
            try:
                dag_bytes = base64.b64decode(payload.dag_json)
                dag_dict = json.loads(dag_bytes.decode())
            except Exception:
                dag_dict = json.loads(payload.dag_json)

            dag_hash = hashlib.sha256(
                json.dumps(dag_dict, sort_keys=True).encode()
            ).hexdigest()
            strategy_id = str(uuid.uuid4())
            dag_for_storage = dag_dict.copy()
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

            compute_ctx, context_mapping, world_list = self._build_compute_context(payload)

            # Atomically perform dedupe (SETNX) and initial storage to avoid race duplicates
            lua = """
            local hash = KEYS[1]
            local sid = ARGV[1]
            local dag = ARGV[2]
            local hashkey = 'dag_hash:' .. hash
            if redis.call('SETNX', hashkey, sid) == 0 then
                local existing = redis.call('GET', hashkey)
                return {existing or '', 1}
            end
            redis.call('HSET', 'strategy:' .. sid, 'dag', dag, 'hash', hash)
            return {sid, 0}
            """
            try:
                try:
                    res = await self.redis.eval(lua, 1, dag_hash, strategy_id, encoded_dag)
                except Exception as _lua_err:
                    # Fallback path for Redis servers that do not support EVAL (e.g., fakeredis)
                    set_res = await self.redis.set(f"dag_hash:{dag_hash}", strategy_id, nx=True)
                    if not set_res:
                        existing = await self.redis.get(f"dag_hash:{dag_hash}")
                        if isinstance(existing, bytes):
                            existing = existing.decode()
                        return str(existing), True
                    await self.redis.hset(
                        f"strategy:{strategy_id}",
                        mapping={"dag": encoded_dag, "hash": dag_hash},
                    )
                    res = [strategy_id, 0]

                # Expect res as table {id, existed_flag}
                if isinstance(res, (list, tuple)) and len(res) >= 2 and int(res[1]) == 1:
                    existing_id = res[0]
                    if isinstance(existing_id, bytes):
                        existing_id = existing_id.decode()
                    return str(existing_id), True
                try:
                    if self.commit_log_writer is not None:
                        record = self._build_commit_log_payload(
                            strategy_id,
                            dag_for_storage,
                            encoded_dag,
                            dag_hash,
                            payload,
                            compute_ctx,
                            world_list,
                        )
                        await self.commit_log_writer.publish_submission(
                            strategy_id,
                            record,
                        )
                except Exception as exc:
                    gw_metrics.lost_requests_total.inc()
                    gw_metrics.lost_requests_total._val = (
                        gw_metrics.lost_requests_total._value.get()
                    )  # type: ignore[attr-defined]
                    await self._rollback_submission(strategy_id, dag_hash)
                    raise HTTPException(
                        status_code=503,
                        detail={
                            "code": "E_COMMITLOG",
                            "message": "commit log unavailable",
                        },
                    ) from exc
                # Enqueue after storage; degradation may redirect the enqueue only
                if self.degrade and self.degrade.level == DegradationLevel.PARTIAL and not self.degrade.dag_ok:
                    self.degrade.local_queue.append(strategy_id)
                else:
                    await self.redis.rpush("strategy_queue", strategy_id)
            except HTTPException:
                raise
            except Exception:
                gw_metrics.lost_requests_total.inc()
                gw_metrics.lost_requests_total._val = gw_metrics.lost_requests_total._value.get()  # type: ignore[attr-defined]
                raise

            if context_mapping:
                await self.redis.hset(
                    f"strategy:{strategy_id}", mapping=context_mapping
                )
            await self.fsm.create(strategy_id, payload.meta)
            return strategy_id, False

    async def status(self, strategy_id: str) -> Optional[str]:
        return await self.fsm.get(strategy_id)

    async def _rollback_submission(self, strategy_id: str, dag_hash: str) -> None:
        try:
            if hasattr(self.redis, "delete"):
                await self.redis.delete(f"dag_hash:{dag_hash}")
                await self.redis.delete(f"strategy:{strategy_id}")
        except Exception:
            pass

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
    ) -> tuple[dict[str, str | None], dict[str, str], list[str]]:
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
        compute_ctx: dict[str, str | None] = {
            "world_id": unique_worlds[0] if unique_worlds else None,
        }
        meta = payload.meta if isinstance(payload.meta, dict) else {}
        for key in (
            "execution_domain",
            "as_of",
            "partition",
            "dataset_fingerprint",
        ):
            val = self._ctx_value(meta.get(key)) if meta else None
            if val:
                compute_ctx[key] = val
        context_mapping: dict[str, str] = {
            f"compute_{k}": v
            for k, v in compute_ctx.items()
            if isinstance(v, str) and v
        }
        return compute_ctx, context_mapping, unique_worlds
