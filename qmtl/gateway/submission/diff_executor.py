from __future__ import annotations

"""Async wrapper for invoking DAG Manager diff operations."""

import asyncio
from typing import Any, Iterable


class DiffExecutor:
    """Run DAG Manager diffs and normalize sentinel/queue_map results."""

    def __init__(self, dagmanager) -> None:
        self._dagmanager = dagmanager

    async def run(
        self,
        *,
        strategy_id: str,
        dag_json: str,
        worlds: list[str],
        fallback_world_id: str | None,
        compute_ctx,
        timeout: float,
        prefer_queue_map: bool,
    ) -> tuple[str | None, dict[str, list[dict[str, Any]]] | None]:
        diff_kwargs = compute_ctx.diff_kwargs()

        async def _invoke(world: str | None):
            return await self._dagmanager.diff(
                strategy_id,
                dag_json,
                world_id=world,
                **diff_kwargs,
            )

        sentinel_id: str | None = None
        queue_map: dict[str, list[dict[str, Any]]] | None = None

        if prefer_queue_map and len(worlds) > 1:
            tasks = [_invoke(world_id) for world_id in worlds]
            chunks = await asyncio.gather(*tasks, return_exceptions=True)
            queue_map = {}
            for chunk in chunks:
                if isinstance(chunk, Exception) or chunk is None:
                    continue
                if not sentinel_id:
                    sentinel_id = getattr(chunk, "sentinel_id", None)
                for key, topic in dict(getattr(chunk, "queue_map", {})).items():
                    node_id = self._node_id_from_partition_key(str(key))
                    lst = queue_map.setdefault(node_id, [])
                    if topic not in [d.get("queue") for d in lst]:
                        lst.append({"queue": topic, "global": False})
            return sentinel_id, queue_map

        world = worlds[0] if worlds else fallback_world_id
        if world is None and prefer_queue_map and not worlds:
            queue_map = {}

        chunk = await asyncio.wait_for(_invoke(world), timeout=timeout)
        if chunk is None:
            return sentinel_id, queue_map

        sentinel_id = getattr(chunk, "sentinel_id", None)
        if prefer_queue_map:
            queue_map = {}
            for key, topic in dict(getattr(chunk, "queue_map", {})).items():
                node_id = self._node_id_from_partition_key(str(key))
                queue_map.setdefault(node_id, []).append(
                    {"queue": topic, "global": False}
                )

        return sentinel_id, queue_map

    def _node_id_from_partition_key(self, identifier: str) -> str:
        base, _, _ = identifier.partition("#")
        token = base or identifier
        if ":" in token:
            return token.rsplit(":", 2)[0]
        return token
