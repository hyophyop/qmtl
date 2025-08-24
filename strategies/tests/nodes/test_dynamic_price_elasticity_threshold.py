import math

import pytest

from strategies.nodes.indicators.dynamic_price_elasticity_threshold import (
    dynamic_price_elasticity_threshold_node,
)


def test_dynamic_price_elasticity_threshold_node_basic():
    data = {
        "delta_q": 100.0,
        "delta_p": 2.0,
        "market_depth": 50.0,
        "order_imbalance": 0.2,
        "theta1": 0.5,
        "theta2": 1.5,
        "gamma": 2.0,
    }
    result = dynamic_price_elasticity_threshold_node(data)
    expected_peti = abs(100.0 / 2.0) / (50.0 + 1e-9)
    expected_alpha = 0.5 * math.exp(expected_peti ** 2.0) + 1.5 * 0.2
    assert result["peti"] == pytest.approx(expected_peti)
    assert result["alpha"] == pytest.approx(expected_alpha)


def test_dynamic_price_elasticity_threshold_node_zero_price_change():
    data = {
        "delta_q": 10.0,
        "delta_p": 0.0,
        "market_depth": 10.0,
        "order_imbalance": -0.1,
        "theta1": 1.0,
        "theta2": 2.0,
    }
    result = dynamic_price_elasticity_threshold_node(data)
    expected_alpha = 1.0 * math.exp(0.0) + 2.0 * (-0.1)
    assert result["peti"] == 0.0
    assert result["alpha"] == pytest.approx(expected_alpha)


def test_dynamic_price_elasticity_threshold_node_defaults():
    data = {
        "delta_q": 50.0,
        "delta_p": 5.0,
        "market_depth": 10.0,
        "order_imbalance": -0.3,
    }
    result = dynamic_price_elasticity_threshold_node(data)
    expected_peti = abs(50.0 / 5.0) / (10.0 + 1e-9)
    expected_alpha = math.exp(expected_peti)
    assert result["peti"] == pytest.approx(expected_peti)
    assert result["alpha"] == pytest.approx(expected_alpha)
