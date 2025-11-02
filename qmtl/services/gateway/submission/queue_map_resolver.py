from __future__ import annotations

"""Fallback queue-map resolution using TagQuery lookups."""

import asyncio
from typing import Any, Iterable


class QueueMapResolver:
    """Build queue maps by querying DAG Manager tag endpoints."""

    def __init__(self, dagmanager) -> None:
        self._dagmanager = dagmanager

    async def build(
        self,
        dag: dict[str, Any],
        worlds: list[str],
        default_world: str | None,
        execution_domain: str | None,
    ) -> dict[str, list[dict[str, Any] | Any]]:
        queue_map: dict[str, list[dict[str, Any] | Any]] = {}
        queries: list[asyncio.Future] = []
        query_targets: list[tuple[str, str | None]] = []

        nodes = dag.get("nodes", [])
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get("node_type") != "TagQueryNode":
                continue
            nid = node.get("node_id")
            if not isinstance(nid, str) or not nid:
                continue
            tags = node.get("tags", [])
            interval = int(node.get("interval", 0))
            match_mode = node.get("match_mode", "any")
            if worlds:
                for world_id in worlds:
                    queries.append(
                        self._dagmanager.get_queues_by_tag(
                            tags, interval, match_mode, world_id, execution_domain
                        )
                    )
                    query_targets.append((nid, world_id))
            else:
                queries.append(
                    self._dagmanager.get_queues_by_tag(
                        tags, interval, match_mode, default_world, execution_domain
                    )
                )
                query_targets.append((nid, default_world))

        results: Iterable[Any] = []
        if queries:
            results = await asyncio.gather(*queries, return_exceptions=True)

        seen: dict[str, set[str]] = {}
        for (nid, _world_id), result in zip(query_targets, results):
            lst = queue_map.setdefault(nid, [])
            seen.setdefault(nid, set())
            if isinstance(result, Exception):
                continue
            for item in result:
                queue_name = (
                    item.get("queue")
                    if isinstance(item, dict)
                    else str(item)
                )
                if queue_name not in seen[nid]:
                    lst.append(item)
                    seen[nid].add(queue_name)

        return queue_map
