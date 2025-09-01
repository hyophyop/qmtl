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

    def init(self, strategy) -> TagQueryManager:
        """Initialize and attach a :class:`TagQueryManager` to ``strategy``."""
        manager = TagQueryManager(self.gateway_url)
        for n in strategy.nodes:
            if isinstance(n, TagQueryNode):
                manager.register(n)
        setattr(strategy, "tag_query_manager", manager)
        return manager

    def apply_queue_map(self, strategy, queue_map: dict[str, object]) -> None:
        """Apply queue mappings to strategy nodes."""
        for node in strategy.nodes:
            prefix = f"{node.node_id}:"
            matches: list[object] = []
            if node.node_id in queue_map:
                matches.append(queue_map[node.node_id])
            matches.extend(v for k, v in queue_map.items() if k.startswith(prefix))

            old_execute = node.execute
            mapping: str | list[str] | None
            if isinstance(node, TagQueryNode):
                merged: list[str] = []
                for m in matches:
                    items = m if isinstance(m, list) else [m]
                    for q in items:
                        if isinstance(q, dict):
                            if q.get("global"):
                                continue
                            val = q.get("queue") or q.get("topic")
                            if val:
                                merged.append(val)
                        else:
                            merged.append(q)
                node.upstreams = merged
                node.execute = bool(merged)
                mapping = merged
            else:
                mapping_val = matches[0] if matches else None
                queue = None
                global_flag = False
                if isinstance(mapping_val, dict):
                    queue = mapping_val.get("queue") or mapping_val.get("topic")
                    global_flag = bool(mapping_val.get("global"))
                else:
                    queue = mapping_val
                if queue:
                    node.execute = False
                    node.kafka_topic = queue  # type: ignore[assignment]
                else:
                    node.execute = not global_flag
                    node.kafka_topic = None
                mapping = queue

            if node.execute != old_execute:
                logger.debug(
                    "execute changed for %s: %s -> %s (mapping=%s)",
                    node.node_id,
                    old_execute,
                    node.execute,
                    mapping,
                )
