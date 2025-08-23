"""Tests for composite alpha indicator."""

import pytest

from qmtl.indicators.composite_alpha import composite_alpha_node


def test_composite_alpha_weighted_mean():
    """Composite alpha uses provided weights for aggregation."""

    def a(data):
        return {"alpha": data["val"]}

    def b(data):
        return {"alpha": data["val"]}

    data = {
        "weights": {"a": 3.0, "b": 1.0},
        "a": {"val": 1.0},
        "b": {"val": -1.0},
    }
    result = composite_alpha_node(data, indicators={"a": a, "b": b})
    assert result["components"] == {"a": 1.0, "b": -1.0}
    assert result["alpha"] == pytest.approx(0.5)


def test_composite_alpha_default_weight():
    """Indicators default to equal weights when none provided."""

    def a(data):
        return {"alpha": 1.0}

    def b(data):
        return {"alpha": 3.0}

    data = {"a": {}, "b": {}}
    result = composite_alpha_node(data, indicators={"a": a, "b": b})
    assert result["alpha"] == pytest.approx(2.0)
