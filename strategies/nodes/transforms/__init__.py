"""Transform node processors."""

from qmtl.transforms import (
    AlphaPerformanceNode,
    TradeOrderPublisherNode,
    TradeSignalGeneratorNode,
    alpha_performance_node,
    publisher_node,
    threshold_signal_node,
    trade_signal_node,
)

__all__ = [
    "sample_transform",
    "alpha_performance_node",
    "AlphaPerformanceNode",
    "publisher_node",
    "TradeOrderPublisherNode",
    "threshold_signal_node",
    "trade_signal_node",
    "TradeSignalGeneratorNode",
]


def sample_transform(value: int) -> int:
    """Modify the indicator value before output."""
    return value - 1
