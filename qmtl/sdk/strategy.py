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

            if getattr(node.cache, "period", None) != node.period:
                if arrow_cache.ARROW_AVAILABLE and os.getenv("QMTL_ARROW_CACHE") == "1":
                    node.cache = arrow_cache.NodeCacheArrow(node.period)
                else:
                    node.cache = NodeCache(node.period)

        self.nodes.extend(nodes)

    # ------------------------------------------------------------------
    # Lifecycle hooks ---------------------------------------------------
    def on_start(self) -> None:  # pragma: no cover - default no-op
        """Called once when the strategy begins running."""

    def on_signal(self, signal) -> None:  # pragma: no cover - default no-op
        """Handle a generated trading signal."""

    def on_fill(self, order, fill) -> None:  # pragma: no cover - default no-op
        """Handle an order fill event."""

    def on_error(self, error: Exception) -> None:  # pragma: no cover - default no-op
        """Handle an unrecoverable error during execution."""

    def on_finish(self) -> None:  # pragma: no cover - default no-op
        """Called when the strategy run completes."""

    def setup(self):
        raise NotImplementedError

    # DAG serialization ---------------------------------------------------
    def serialize(self) -> dict:
        """Serialize strategy DAG using node IDs."""
        return {
            "nodes": [node.to_dict() for node in self.nodes],
        }


def buy_signal(condition: bool, target_percent: float = 1.0) -> dict:
    """Convenience helper to create a BUY/HOLD signal.

    Parameters
    ----------
    condition:
        If ``True`` a BUY action is returned; otherwise ``HOLD``.
    target_percent:
        Target portfolio percentage when buying.
    """

    if condition:
        return {"action": "BUY", "target_percent": float(target_percent)}
    return {"action": "HOLD"}
