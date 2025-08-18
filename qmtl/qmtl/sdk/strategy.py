from .util import parse_interval, parse_period
from . import arrow_cache
from .node import NodeCache
import os


class Strategy:
    """Base class for strategies."""

    def __init__(self, *, default_interval=None, default_period=None):
        self.nodes = []
        self.default_interval = (
            parse_interval(default_interval) if default_interval is not None else None
        )
        self.default_period = (
            parse_period(default_period) if default_period is not None else None
        )

    def add_nodes(self, nodes):
        for node in nodes:
            if node.interval is None:
                if self.default_interval is None:
                    raise ValueError("interval not specified and no default_interval set")
                node.interval = self.default_interval
            node.interval = parse_interval(node.interval)

            if node.period is None:
                if self.default_period is None:
                    raise ValueError("period not specified and no default_period set")
                node.period = self.default_period
            node.period = parse_period(node.period)

            current_size = getattr(node.cache, "window_size", getattr(node.cache, "period", None))
            if current_size != node.period:
                if arrow_cache.ARROW_AVAILABLE and os.getenv("QMTL_ARROW_CACHE") == "1":
                    node.cache = arrow_cache.NodeCacheArrow(node.period)
                else:
                    node.cache = NodeCache(window_size=node.period)

        self.nodes.extend(nodes)

    def setup(self):
        raise NotImplementedError

    # DAG serialization ---------------------------------------------------
    def serialize(self) -> dict:
        """Serialize strategy DAG using node IDs."""
        return {
            "nodes": [node.to_dict() for node in self.nodes],
        }
