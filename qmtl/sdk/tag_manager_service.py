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
            mapping = queue_map.get(node.node_id)
            old_execute = node.execute
            if isinstance(node, TagQueryNode):
                if isinstance(mapping, list):
                    node.upstreams = list(mapping)
                    node.execute = bool(mapping)
                else:
                    node.upstreams = []
                    node.execute = False
            else:
                if mapping:
                    node.execute = False
                    node.kafka_topic = mapping  # type: ignore[assignment]
                else:
                    node.execute = True
                    node.kafka_topic = None
            if node.execute != old_execute:
                logger.debug(
                    "execute changed for %s: %s -> %s (mapping=%s)",
                    node.node_id,
                    old_execute,
                    node.execute,
                    mapping,
                )
