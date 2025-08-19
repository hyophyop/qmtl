"""Transform node processors."""

from .alpha_performance import AlphaPerformanceNode, alpha_performance_node
from .publisher import TradeOrderPublisherNode, publisher_node

__all__ = [
    "sample_transform",
    "alpha_performance_node",
    "AlphaPerformanceNode",
    "publisher_node",
    "TradeOrderPublisherNode",
]


def sample_transform(value: int) -> int:
    """Modify the indicator value before output."""
    return value - 1
