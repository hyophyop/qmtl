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

    def apply_queue_map(self, strategy, queue_map: dict[str, str | list[str]]) -> None:
        """Apply queue mappings to strategy nodes."""
        for node in strategy.nodes:
            prefix = f"{node.node_id}:"
            matches: list[str | list[str]] = []
            if node.node_id in queue_map:
                matches.append(queue_map[node.node_id])
            matches.extend(v for k, v in queue_map.items() if k.startswith(prefix))

            old_execute = node.execute
            mapping: str | list[str] | None
            if isinstance(node, TagQueryNode):
                merged: list[str] = []
                for m in matches:
                    if isinstance(m, list):
                        merged.extend(m)
                    else:
                        merged.append(m)
                node.upstreams = merged
                node.execute = True  # always execute tag queries
                mapping = merged
            else:
                mapping_val = matches[0] if matches else None
                if mapping_val:
                    node.execute = False
                    node.kafka_topic = mapping_val  # type: ignore[assignment]
                else:
                    node.execute = True
                    node.kafka_topic = None
                mapping = mapping_val

            if node.execute != old_execute:
                logger.debug(
                    "execute changed for %s: %s -> %s (mapping=%s)",
                    node.node_id,
                    old_execute,
                    node.execute,
                    mapping,
                )
