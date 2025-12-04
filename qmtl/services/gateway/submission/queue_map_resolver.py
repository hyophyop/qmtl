from __future__ import annotations

"""Fallback queue-map resolution using TagQuery lookups."""

import asyncio
from dataclasses import dataclass
from typing import Any, Iterable, Iterator

from qmtl.foundation.common.tagquery import canonical_tag_query_params_from_node


@dataclass(frozen=True)
class _TagQueryNode:
    node_id: str
    tags: list[Any]
    interval: int
    match_mode: str


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
        nodes = list(self._iter_tag_queries(dag))
        queries, query_targets = self._schedule_queries(
            nodes, worlds, default_world, execution_domain
        )

        results: Iterable[Any] = []
        if queries:
            results = await asyncio.gather(*queries, return_exceptions=True)

        seen: dict[str, set[str]] = {}
        for (nid, _world_id), result in zip(query_targets, results):
            self._collect_results(queue_map, seen, nid, result)

        return queue_map

    def _iter_tag_queries(self, dag: dict[str, Any]) -> Iterator[_TagQueryNode]:
        for node in dag.get("nodes", []):
            if not isinstance(node, dict):
                continue
            if node.get("node_type") != "TagQueryNode":
                continue
            node_id = node.get("node_id")
            if not isinstance(node_id, str) or not node_id:
                continue
            try:
                spec = canonical_tag_query_params_from_node(
                    node, require_tags=True, require_interval=True
                )
            except ValueError:
                continue
            tags = spec.get("query_tags", [])
            interval = int(spec.get("interval") or 0)
            match_mode = spec.get("match_mode", "any")
            yield _TagQueryNode(
                node_id=node_id,
                tags=tags,
                interval=interval,
                match_mode=match_mode,
            )

    def _schedule_queries(
        self,
        nodes: list[_TagQueryNode],
        worlds: list[str],
        default_world: str | None,
        execution_domain: str | None,
    ) -> tuple[list[asyncio.Future], list[tuple[str, str | None]]]:
        queries: list[asyncio.Future] = []
        targets: list[tuple[str, str | None]] = []
        if not nodes:
            return queries, targets

        for node in nodes:
            if worlds:
                for world_id in worlds:
                    queries.append(
                        self._dagmanager.get_queues_by_tag(
                            node.tags, node.interval, node.match_mode, world_id, execution_domain
                        )
                    )
                    targets.append((node.node_id, world_id))
            else:
                queries.append(
                    self._dagmanager.get_queues_by_tag(
                        node.tags, node.interval, node.match_mode, default_world, execution_domain
                    )
                )
                targets.append((node.node_id, default_world))

        return queries, targets

    def _collect_results(
        self,
        queue_map: dict[str, list[dict[str, Any] | Any]],
        seen: dict[str, set[str]],
        node_id: str,
        result: Any,
    ) -> None:
        lst = queue_map.setdefault(node_id, [])
        seen.setdefault(node_id, set())
        if isinstance(result, Exception):
            return
        for item in result:
            queue_name = item.get("queue") if isinstance(item, dict) else str(item)
            if not isinstance(queue_name, str):
                continue
            if queue_name not in seen[node_id]:
                lst.append(item)
                seen[node_id].add(queue_name)
