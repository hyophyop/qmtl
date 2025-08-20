"""Tests for transform utilities."""

import math
import pytest

from qmtl.transforms.utils import (
    validate_numeric,
    validate_numeric_sequence,
    normalized_difference,
    create_imbalance_node,
    compute_statistics,
    create_period_statistics_node,
    create_period_delta_node,
)
from qmtl.sdk.node import SourceNode
from qmtl.sdk.cache_view import CacheView


def test_validate_numeric():
    """Test numeric validation."""
    assert validate_numeric(1.0) is True
    assert validate_numeric(1) is True
    assert validate_numeric(0.0) is True
    assert validate_numeric(-1.0) is True
    
    assert validate_numeric(math.nan) is False
    assert validate_numeric("1.0") is False
    assert validate_numeric(None) is False


def test_validate_numeric_sequence():
    """Test numeric sequence validation."""
    assert validate_numeric_sequence([1.0, 2.0, 3.0]) is True
    assert validate_numeric_sequence([1, 2, 3]) is True
    assert validate_numeric_sequence([]) is True
    
    assert validate_numeric_sequence([1.0, math.nan, 3.0]) is False
    assert validate_numeric_sequence([1.0, "2", 3.0]) is False
    assert validate_numeric_sequence("not_a_sequence") is False


def test_normalized_difference():
    """Test normalized difference calculation."""
    # Basic cases
    assert normalized_difference(60, 40) == 0.2
    assert normalized_difference(30, 10) == 0.5
    assert normalized_difference(10, 30) == -0.5
    assert normalized_difference(0, 0) is None
    
    # Invalid inputs
    assert normalized_difference(math.nan, 40) is None
    assert normalized_difference(60, math.nan) is None
    assert normalized_difference("60", 40) is None


def test_create_imbalance_node():
    """Test generic imbalance node creation."""
    node_a = SourceNode(interval="1s", period=1, config={"id": "a"})
    node_b = SourceNode(interval="1s", period=1, config={"id": "b"})
    
    imbalance_node = create_imbalance_node(node_a, node_b, name="test_imbalance")
    
    # Test with valid data
    data = {
        node_a.node_id: {1: [(0, 60)]},
        node_b.node_id: {1: [(0, 40)]},
    }
    view = CacheView(data)
    result = imbalance_node.compute_fn(view)
    assert result == 0.2
    
    # Test with empty data
    empty_data = {node_a.node_id: {1: []}, node_b.node_id: {1: []}}
    empty_view = CacheView(empty_data)
    result = imbalance_node.compute_fn(empty_view)
    assert result is None


def test_compute_statistics():
    """Test statistics computation."""
    # Valid cases
    mean, std = compute_statistics([1.0, 2.0, 3.0])
    assert mean == 2.0
    assert round(std, 2) == 0.82
    
    # Edge cases
    assert compute_statistics([]) is None
    
    mean, std = compute_statistics([5.0])
    assert mean == 5.0
    assert std == 0.0


def test_create_period_statistics_node():
    """Test period statistics node creation."""
    source = SourceNode(interval="1s", period=3, config={"id": "source"})
    
    # Test mean only
    mean_node = create_period_statistics_node(source, period=3, stat_type="mean")
    data = {source.node_id: {1: [(0, 1), (1, 2), (2, 3)]}}
    view = CacheView(data)
    result = mean_node.compute_fn(view)
    assert result == 2.0
    
    # Test std only
    std_node = create_period_statistics_node(source, period=3, stat_type="std")
    result = std_node.compute_fn(view)
    assert round(result, 2) == 0.82
    
    # Test both
    both_node = create_period_statistics_node(source, period=3, stat_type="both")
    result = both_node.compute_fn(view)
    assert result["mean"] == 2.0
    assert round(result["std"], 2) == 0.82
    
    # Test insufficient data
    short_data = {source.node_id: {1: [(0, 1), (1, 2)]}}
    short_view = CacheView(short_data)
    result = both_node.compute_fn(short_view)
    assert result is None


def test_create_period_delta_node():
    """Test period delta node creation."""
    source = SourceNode(interval="1s", period=3, config={"id": "source"})
    
    # Test rate of change style transformation
    def percentage_change(start, end):
        if start == 0:
            return None
        return (end - start) / start
    
    roc_node = create_period_delta_node(source, percentage_change, period=2)
    data = {source.node_id: {1: [(0, 1), (1, 3)]}}
    view = CacheView(data)
    result = roc_node.compute_fn(view)
    assert result == 2.0
    
    # Test absolute change style transformation
    def absolute_change(start, end):
        return end - start
    
    abs_node = create_period_delta_node(source, absolute_change, period=2)
    result = abs_node.compute_fn(view)
    assert result == 2
    
    # Test insufficient data
    short_data = {source.node_id: {1: [(0, 1)]}}
    short_view = CacheView(short_data)
    result = roc_node.compute_fn(short_view)
    assert result is None