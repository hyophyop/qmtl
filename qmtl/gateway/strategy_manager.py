from __future__ import annotations

import base64
import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Optional

import redis.asyncio as redis
from opentelemetry import trace

from .database import Database
from .fsm import StrategyFSM
from .degradation import DegradationManager, DegradationLevel
from . import metrics as gw_metrics
from .models import StrategySubmit

tracer = trace.get_tracer(__name__)


@dataclass
class StrategyManager:
    redis: redis.Redis
    database: Database
    fsm: StrategyFSM
    degrade: Optional[DegradationManager] = None
    insert_sentinel: bool = True

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
                # Enqueue after storage; degradation may redirect the enqueue only
                if self.degrade and self.degrade.level == DegradationLevel.PARTIAL and not self.degrade.dag_ok:
                    self.degrade.local_queue.append(strategy_id)
                else:
                    await self.redis.rpush("strategy_queue", strategy_id)
            except Exception:
                gw_metrics.lost_requests_total.inc()
                gw_metrics.lost_requests_total._val = gw_metrics.lost_requests_total._value.get()  # type: ignore[attr-defined]
                raise

            def _ctx_value(value):
                if isinstance(value, bytes):
                    value = value.decode()
                if value is None:
                    return None
                if isinstance(value, (str, int, float)):
                    text = str(value).strip()
                    return text or None
                return None

            context_mapping: dict[str, str] = {}
            world_candidates: list[str] = []
            if payload.world_id:
                world_candidates.append(payload.world_id)
            wid_list = getattr(payload, "world_ids", None)
            if wid_list:
                world_candidates.extend([w for w in wid_list if w])
            if world_candidates:
                world_val = _ctx_value(world_candidates[0])
                if world_val:
                    context_mapping["compute_world_id"] = world_val

            meta = payload.meta if isinstance(payload.meta, dict) else {}
            for key in (
                "execution_domain",
                "as_of",
                "partition",
                "dataset_fingerprint",
            ):
                if not meta:
                    break
                val = _ctx_value(meta.get(key))
                if val:
                    context_mapping[f"compute_{key}"] = val

            if context_mapping:
                await self.redis.hset(
                    f"strategy:{strategy_id}", mapping=context_mapping
                )
            await self.fsm.create(strategy_id, payload.meta)
            return strategy_id, False

    async def status(self, strategy_id: str) -> Optional[str]:
        return await self.fsm.get(strategy_id)
