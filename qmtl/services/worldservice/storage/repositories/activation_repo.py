"""Persistent repository for activation state stored in redis."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict

from ..models import WorldActivation
from .base import AuditLogger, RedisClient


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


class PersistentActivationRepository:
    """Manages activation documents for persistent storage."""

    def __init__(self, redis_client: RedisClient, audit: AuditLogger) -> None:
        self._redis = redis_client
        self._audit = audit

    async def get(
        self, world_id: str, *, strategy_id: str | None = None, side: str | None = None
    ) -> Dict[str, Any]:
        state = await self._load(world_id)
        if strategy_id and side:
            entry = state["state"].get(strategy_id, {}).get(side)
            payload: Dict[str, Any] = {"version": state["version"]}
            if entry:
                payload.update(entry)
            return payload
        return {"version": state["version"], "state": state["state"]}

    async def snapshot(self, world_id: str) -> WorldActivation:
        state = await self._load(world_id)
        return WorldActivation(version=state["version"], state=state["state"])

    async def restore(self, world_id: str, snapshot: WorldActivation) -> None:
        payload = {"version": snapshot.version, "state": snapshot.state}
        await self._redis.set(self._key(world_id), json.dumps(payload))

    async def update(self, world_id: str, payload: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
        state = await self._load(world_id)
        state["version"] += 1
        strategy_id = str(payload["strategy_id"])
        side = str(payload["side"])
        ts = payload.get("ts") or _utc_now()
        etag = f"act:{world_id}:{strategy_id}:{side}:{state['version']}"
        entry = {
            "active": bool(payload.get("active", False)),
            "weight": float(payload.get("weight", 1.0)),
            "freeze": bool(payload.get("freeze", False)),
            "drain": bool(payload.get("drain", False)),
            "effective_mode": payload.get("effective_mode"),
            "run_id": payload.get("run_id"),
            "ts": ts,
            "etag": etag,
        }
        state["state"].setdefault(strategy_id, {})[side] = entry
        await self._redis.set(self._key(world_id), json.dumps(state))
        audit_payload = {
            "event": "activation_updated",
            "version": state["version"],
            "strategy_id": strategy_id,
            "side": side,
        }
        audit_payload.update(entry)
        await self._audit(world_id, audit_payload)
        return state["version"], dict(entry)

    async def clear(self, world_id: str) -> None:
        await self._redis.delete(self._key(world_id))

    def _key(self, world_id: str) -> str:
        return f"world:{world_id}:activation"

    async def _load(self, world_id: str) -> Dict[str, Any]:
        raw = await self._redis.get(self._key(world_id))
        if not raw:
            return {"version": 0, "state": {}}
        if isinstance(raw, bytes):
            raw = raw.decode()
        return json.loads(raw)
