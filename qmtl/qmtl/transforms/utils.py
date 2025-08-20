"""Utility functions for transform operations.

This module provides reusable utilities to reduce code duplication
across transform functions while maintaining readability and clarity.
"""

from __future__ import annotations

import math
from typing import Iterable

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def validate_numeric(value) -> bool:
    """Validate that a value is a valid number (not NaN)."""
    return isinstance(value, (int, float)) and not math.isnan(value)


def validate_numeric_sequence(seq: Iterable[float]) -> bool:
    """Validate that all values in a sequence are valid numbers."""
    try:
        return all(validate_numeric(v) for v in seq)
    except TypeError:
        return False


def normalized_difference(a: float, b: float) -> float | None:
    """Calculate normalized difference: (a - b) / (a + b).
    
    This is the common imbalance calculation pattern used across
    order book imbalance, execution imbalance, and order flow imbalance.
    
    Args:
        a: First value (e.g., buy volume, bid volume)
        b: Second value (e.g., sell volume, ask volume)
        
    Returns:
        Normalized difference or None if total is zero
    """
    if not (validate_numeric(a) and validate_numeric(b)):
        return None
    
    total = a + b
    if total == 0:
        return None
    
    return (a - b) / total


def create_imbalance_node(
    node_a: Node,
    node_b: Node,
    *,
    interval: int | None = None,
    name: str | None = None,
) -> Node:
    """Create a node that computes normalized difference between two input nodes.
    
    This generalizes the pattern used by order_book_imbalance_node,
    execution_imbalance_node, and order_flow_imbalance_node.
    
    Args:
        node_a: First input node (e.g., buy volume, bid volume)
        node_b: Second input node (e.g., sell volume, ask volume)
        interval: Optional interval override
        name: Optional node name
        
    Returns:
        Node computing (a - b) / (a + b) from latest values
    """
    interval = interval or node_a.interval

    def compute(view: CacheView):
        data_a = view[node_a][interval]
        data_b = view[node_b][interval]
        # Check if the underlying data is empty
        if not data_a._data or not data_b._data:
            return None
        
        a = data_a[-1][1]
        b = data_b[-1][1]
        return normalized_difference(a, b)

    return Node(
        input=[node_a, node_b],
        compute_fn=compute,
        name=name or "imbalance",
        interval=interval,
    )


def compute_statistics(values: list[float]) -> tuple[float, float] | None:
    """Compute mean and standard deviation from a list of values.
    
    Args:
        values: List of numeric values
        
    Returns:
        Tuple of (mean, std) or None if values is empty
    """
    if not values:
        return None
    
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std = math.sqrt(variance)
    return mean, std


def create_period_statistics_node(
    source: Node,
    period: int,
    *,
    stat_type: str = "both",
    name: str | None = None,
) -> Node:
    """Create a node that computes statistics over a period.
    
    Args:
        source: Input node
        period: Number of values to include in calculation
        stat_type: "mean", "std", or "both" 
        name: Optional node name
        
    Returns:
        Node computing the requested statistics
    """
    def compute(view: CacheView):
        values = [v for _, v in view[source][source.interval][-period:]]
        if len(values) < period:
            return None
        
        if stat_type == "mean":
            return sum(values) / len(values)
        elif stat_type == "std":
            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / len(values)
            return math.sqrt(variance)
        else:  # both
            stats = compute_statistics(values)
            if stats is None:
                return None
            mean, std = stats
            return {"mean": mean, "std": std}

    return Node(
        input=source,
        compute_fn=compute,
        name=name or f"{stat_type}_statistics",
        interval=source.interval,
        period=period,
    )


__all__ = [
    "validate_numeric",
    "validate_numeric_sequence", 
    "normalized_difference",
    "create_imbalance_node",
    "compute_statistics",
    "create_period_statistics_node",
]