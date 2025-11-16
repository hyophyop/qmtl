from __future__ import annotations

import logging
from typing import Optional

from .tagquery_manager import TagQueryManager
from .node import TagQueryNode

logger = logging.getLogger(__name__)


class TagManagerService:
    """Manage tag queries and queue mappings for a strategy."""

    def __init__(self, gateway_url: str | None) -> None:
        self.gateway_url = gateway_url

    def init(
        self,
        strategy,
        *,
        world_id: str | None = None,
        strategy_id: str | None = None,
    ) -> TagQueryManager:
        """Initialize and attach a :class:`TagQueryManager` to ``strategy``."""
        manager = TagQueryManager(
            self.gateway_url, world_id=world_id, strategy_id=strategy_id
        )
        for n in strategy.nodes:
            if isinstance(n, TagQueryNode):
                manager.register(n)
            n.world_id = world_id
        setattr(strategy, "tag_query_manager", manager)
        return manager

    def apply_queue_map(self, strategy, queue_map: dict[str, object]) -> None:
        """Apply queue mappings to strategy nodes."""
        for node in strategy.nodes:
            matches = self._collect_matches(node, queue_map)
            old_execute = node.execute
            mapping = (
                self._apply_tag_node_mapping(node, matches)
                if isinstance(node, TagQueryNode)
                else self._apply_generic_node_mapping(node, matches)
            )
            self._log_execute_change(node, old_execute, mapping)

    def _collect_matches(self, node, queue_map: dict[str, object]) -> list[object]:
        prefix = f"{node.node_id}:"
        matches: list[object] = []
        if node.node_id in queue_map:
            matches.append(queue_map[node.node_id])
        matches.extend(v for k, v in queue_map.items() if k.startswith(prefix))
        return matches

    def _apply_tag_node_mapping(
        self, node: TagQueryNode, matches: list[object]
    ) -> list[str]:
        merged: list[str] = []
        for match in matches:
            items = match if isinstance(match, list) else [match]
            for queue in items:
                if isinstance(queue, dict):
                    if queue.get("global"):
                        continue
                    value = queue.get("queue")
                    if value:
                        merged.append(value)
                elif isinstance(queue, str):
                    merged.append(queue)
                else:
                    continue
        node.upstreams = merged
        node.execute = bool(merged)
        return merged

    def _apply_generic_node_mapping(
        self, node, matches: list[object]
    ) -> str | None:
        mapping_val = matches[0] if matches else None
        queue = None
        global_flag = False
        if isinstance(mapping_val, dict):
            queue = mapping_val.get("queue")
            global_flag = bool(mapping_val.get("global"))
        else:
            queue = mapping_val
        if queue:
            node.execute = False
            node.kafka_topic = queue  # type: ignore[assignment]
        else:
            node.execute = not global_flag
            node.kafka_topic = None
        return queue

    def _log_execute_change(self, node, old_execute: bool, mapping) -> None:
        if node.execute == old_execute:
            return
        logger.debug(
            "execute changed for %s: %s -> %s (mapping=%s)",
            node.node_id,
            old_execute,
            node.execute,
            mapping,
        )
