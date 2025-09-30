from __future__ import annotations

from typing import Any

import redis.asyncio as redis

from .degradation import DegradationLevel, DegradationManager


class StrategyStorage:
    """Persist strategy submissions and enforce deduplication."""

    _LUA_DEDUPE = """
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

    def __init__(self, redis_client: redis.Redis):
        self._redis = redis_client

    async def save_unique(
        self, strategy_id: str, dag_hash: str, encoded_dag: str
    ) -> tuple[str, bool]:
        try:
            res = await self._redis.eval(
                self._LUA_DEDUPE, 1, dag_hash, strategy_id, encoded_dag
            )
        except Exception:
            res = await self._fallback_dedupe(strategy_id, dag_hash, encoded_dag)

        return self._parse_dedupe_result(res)

    async def rollback(self, strategy_id: str, dag_hash: str) -> None:
        try:
            if hasattr(self._redis, "delete"):
                await self._redis.delete(f"dag_hash:{dag_hash}")
                await self._redis.delete(f"strategy:{strategy_id}")
        except Exception:
            # best-effort cleanup; failures are intentionally ignored
            pass

    async def _fallback_dedupe(
        self, strategy_id: str, dag_hash: str, encoded_dag: str
    ) -> list[Any]:
        existing = await self._redis.get(f"dag_hash:{dag_hash}")
        if existing is not None:
            if isinstance(existing, bytes):
                existing = existing.decode()
            return [existing or "", 1]
        inserted = await self._redis.set(
            f"dag_hash:{dag_hash}", strategy_id, nx=True
        )
        if not inserted:
            existing = await self._redis.get(f"dag_hash:{dag_hash}")
            if isinstance(existing, bytes):
                existing = existing.decode()
            return [existing or "", 1]
        await self._redis.hset(
            f"strategy:{strategy_id}", mapping={"dag": encoded_dag, "hash": dag_hash}
        )
        return [strategy_id, 0]

    def _parse_dedupe_result(self, result: Any) -> tuple[str, bool]:
        if (
            isinstance(result, (list, tuple))
            and len(result) >= 2
            and int(result[1]) == 1
        ):
            existing_id = result[0]
            if isinstance(existing_id, bytes):
                existing_id = existing_id.decode()
            return str(existing_id), True
        if isinstance(result, (list, tuple)) and result:
            value = result[0]
            if isinstance(value, bytes):
                value = value.decode()
            return str(value), False
        if isinstance(result, bytes):
            return result.decode(), False
        return str(result), False


class StrategyQueue:
    """Enqueue strategies for downstream processing."""

    def __init__(self, redis_client: redis.Redis):
        self._redis = redis_client

    async def enqueue(
        self, strategy_id: str, degradation: DegradationManager | None = None
    ) -> None:
        if (
            degradation
            and degradation.level == DegradationLevel.PARTIAL
            and not degradation.dag_ok
        ):
            degradation.local_queue.append(strategy_id)
            return
        await self._redis.rpush("strategy_queue", strategy_id)


__all__ = ["StrategyQueue", "StrategyStorage"]
