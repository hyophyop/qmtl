import math

import pytest

from strategies.nodes.indicators.llrti import llrti_node
from strategies.nodes.indicators.latent_liquidity_alpha import (
    latent_liquidity_alpha_node,
)


def test_llrti_node_triggers_on_price_move():
    data = {
        "depth_changes": [1.0, -0.5],
        "price_change": 0.02,
        "delta_t": 2.0,
        "delta": 0.01,
    }
    result = llrti_node(data)
    assert result["llrti"] == pytest.approx(0.25)


def test_llrti_node_zero_when_below_threshold():
    data = {
        "depth_changes": [1.0],
        "price_change": 0.005,
        "delta_t": 1.0,
        "delta": 0.01,
    }
    assert llrti_node(data)["llrti"] == 0.0


def test_llrti_node_zero_at_threshold():
    data = {
        "depth_changes": [1.0],
        "price_change": 0.01,
        "delta_t": 1.0,
        "delta": 0.01,
    }
    assert llrti_node(data)["llrti"] == 0.0


def test_latent_liquidity_alpha_node_computes_value():
    alpha_data = {
        "llrti": 0.25,
        "gamma": 2.0,
        "theta1": 1.0,
        "theta2": 2.0,
        "exec_imbalance_deriv": 0.1,
    }
    result = latent_liquidity_alpha_node(alpha_data)
    expected = 1.0 * math.log(1 + abs(0.25) ** 2.0) + 2.0 * 0.1
    assert result["alpha"] == pytest.approx(expected)


def test_latent_liquidity_alpha_node_negative_derivative():
    alpha_data = {
        "llrti": 0.25,
        "gamma": 2.0,
        "theta1": 1.0,
        "theta2": 2.0,
        "exec_imbalance_deriv": -0.1,
    }
    result = latent_liquidity_alpha_node(alpha_data)
    expected = 1.0 * math.log(1 + abs(0.25) ** 2.0) - 0.2
    assert result["alpha"] == pytest.approx(expected)
