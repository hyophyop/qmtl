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
            existing = await self.redis.get(f"dag_hash:{dag_hash}")
            if existing:
                existing_id = existing.decode() if isinstance(existing, bytes) else existing
                return existing_id, True

            strategy_id = str(uuid.uuid4())
            dag_for_storage = dag_dict.copy()
            if self.insert_sentinel:
                sentinel = {
                    "node_type": "VersionSentinel",
                    "node_id": f"{strategy_id}-sentinel",
                }
                dag_for_storage.setdefault("nodes", []).append(sentinel)
            encoded_dag = base64.b64encode(json.dumps(dag_for_storage).encode()).decode()

            try:
                if self.degrade and self.degrade.level == DegradationLevel.PARTIAL and not self.degrade.dag_ok:
                    self.degrade.local_queue.append(strategy_id)
                else:
                    await self.redis.rpush("strategy_queue", strategy_id)
                await self.redis.hset(
                    f"strategy:{strategy_id}",
                    mapping={"dag": encoded_dag, "hash": dag_hash},
                )
                await self.redis.set(f"dag_hash:{dag_hash}", strategy_id)
            except Exception:
                gw_metrics.lost_requests_total.inc()
                gw_metrics.lost_requests_total._val = gw_metrics.lost_requests_total._value.get()  # type: ignore[attr-defined]
                raise
            await self.fsm.create(strategy_id, payload.meta)
            return strategy_id, False

    async def status(self, strategy_id: str) -> Optional[str]:
        return await self.fsm.get(strategy_id)
