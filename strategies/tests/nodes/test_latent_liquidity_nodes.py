import math
import pytest

from strategies.nodes.indicators.llrti import llrti_node
from strategies.nodes.indicators.latent_liquidity_alpha import (
    latent_liquidity_alpha_node,
)
from strategies.nodes.indicators.latent_liquidity_cache import CACHE_NS


def _llrti(depth_changes, price_change, delta_t, delta):
    if delta_t <= 0 or abs(price_change) <= delta:
        return 0.0
    return sum(depth_changes) / delta_t


def test_llrti_node_triggers_on_price_move_and_updates_cache():
    cache: dict = {}
    llrti_node(
        {
            "time": 0,
            "side": "buy",
            "level": 0,
            "depth_change": 1.0,
            "price_change": 0.0,
            "delta_t": 1.0,
            "delta": 0.01,
            "beta": (0.0, 1.0),
            "spread": 0.02,
            "taker_fee": 0.001,
            "impact": 0.0,
        },
        cache,
    )
    result = llrti_node(
        {
            "time": 1,
            "side": "buy",
            "level": 0,
            "depth_change": -0.5,
            "price_change": 0.02,
            "delta_t": 2.0,
            "delta": 0.01,
            "beta": (0.0, 1.0),
            "spread": 0.02,
            "taker_fee": 0.001,
            "impact": 0.0,
            "jump_sizes": [0.01, -0.03],
        },
        cache,
    )
    expected = _llrti([1.0, -0.5], 0.02, 2.0, 0.01)
    assert result["llrti"] == pytest.approx(expected)
    expected_hazard = 1.0 / (1.0 + math.exp(-expected))
    expected_jump = (abs(0.01) + abs(-0.03)) / 2
    expected_hazard_jump = expected_hazard * expected_jump
    assert result["hazard"] == pytest.approx(expected_hazard)
    assert result["expected_jump"] == pytest.approx(expected_jump)
    assert result["hazard_jump"] == pytest.approx(expected_hazard_jump)
    assert result["cost"] == pytest.approx(0.011)
    ns = cache[CACHE_NS]
    assert ns["depth_changes"][(0, "buy", 0)] == 1.0
    assert ns["depth_changes"][(1, "buy", 0)] == -0.5
    assert ns["llrti_hazard"][(1, "buy", 0)] == pytest.approx(expected_hazard)
    assert ns["llrti_hazard_jump"][(1, "buy", 0)] == pytest.approx(
        expected_hazard_jump
    )


def test_llrti_node_zero_when_below_threshold():
    cache: dict = {}
    data = {
        "time": 0,
        "side": "buy",
        "level": 0,
        "depth_change": 1.0,
        "price_change": 0.005,
        "delta_t": 1.0,
        "delta": 0.01,
        "beta": (0.0, 1.0),
    }
    expected = _llrti([1.0], 0.005, 1.0, 0.01)
    result = llrti_node(data, cache)
    assert result["llrti"] == expected
    assert result["hazard"] == pytest.approx(0.5)
    assert result["hazard_jump"] == pytest.approx(0.0)


def test_llrti_node_zero_at_threshold():
    cache: dict = {}
    data = {
        "time": 0,
        "side": "buy",
        "level": 0,
        "depth_change": 1.0,
        "price_change": 0.01,
        "delta_t": 1.0,
        "delta": 0.01,
        "beta": (0.0, 1.0),
    }
    expected = _llrti([1.0], 0.01, 1.0, 0.01)
    result = llrti_node(data, cache)
    assert result["llrti"] == expected
    assert result["hazard"] == pytest.approx(0.5)
    assert result["hazard_jump"] == pytest.approx(0.0)


def test_latent_liquidity_alpha_node_computes_value_and_updates_cache():
    cache: dict = {}
    llrti_node(
        {
            "time": 0,
            "side": "buy",
            "level": 0,
            "depth_change": 1.0,
            "price_change": 0.0,
            "delta_t": 1.0,
            "delta": 0.01,
            "beta": (0.0, 1.0),
            "spread": 0.02,
            "taker_fee": 0.001,
            "impact": 0.0,
        },
        cache,
    )
    llrti_res = llrti_node(
        {
            "time": 1,
            "side": "buy",
            "level": 0,
            "depth_change": -0.5,
            "price_change": 0.02,
            "delta_t": 2.0,
            "delta": 0.01,
            "beta": (0.0, 1.0),
            "spread": 0.02,
            "taker_fee": 0.001,
            "impact": 0.0,
            "jump_sizes": [0.02, -0.04],
        },
        cache,
    )
    llrti_val = llrti_res["llrti"]
    hazard_jump = llrti_res["hazard_jump"]
    cost = llrti_res["cost"]

    imb_deriv = 0.25

    result = latent_liquidity_alpha_node(
        {
            "time": 1,
            "side": "buy",
            "level": 0,
            "gamma": 2.0,
            "theta1": 1.0,
            "theta2": 2.0,
            "exec_imbalance_deriv": imb_deriv,
            "hazard_jump": hazard_jump,
            "cost": cost,
        },
        cache,
    )
    expected_alpha = 1.0 * math.log(1 + abs(llrti_val) ** 2.0) + 2.0 * abs(
        imb_deriv
    )
    direction = 1.0
    expected_scaled = direction * hazard_jump * expected_alpha / (1.0 + cost)
    assert result["alpha"] == pytest.approx(expected_scaled)
    ns = cache[CACHE_NS]
    assert ns["exec_delta"][(1, "buy", 0)] == imb_deriv
    assert ns["llrti_hazard_jump"][(1, "buy", 0)] == pytest.approx(
        hazard_jump
    )


def test_latent_liquidity_alpha_node_negative_derivative():
    cache: dict = {}
    llrti_node(
        {
            "time": 0,
            "side": "buy",
            "level": 0,
            "depth_change": 1.0,
            "price_change": 0.0,
            "delta_t": 1.0,
            "delta": 0.01,
            "beta": (0.0, 1.0),
            "spread": 0.02,
            "taker_fee": 0.001,
            "impact": 0.0,
        },
        cache,
    )
    llrti_res = llrti_node(
        {
            "time": 1,
            "side": "buy",
            "level": 0,
            "depth_change": -0.5,
            "price_change": 0.02,
            "delta_t": 2.0,
            "delta": 0.01,
            "beta": (0.0, 1.0),
            "spread": 0.02,
            "taker_fee": 0.001,
            "impact": 0.0,
            "jump_sizes": [0.02, -0.04],
        },
        cache,
    )
    llrti_val = llrti_res["llrti"]
    hazard_jump = llrti_res["hazard_jump"]
    cost = llrti_res["cost"]

    imb_deriv = -0.25

    result = latent_liquidity_alpha_node(
        {
            "time": 1,
            "side": "buy",
            "level": 0,
            "gamma": 2.0,
            "theta1": 1.0,
            "theta2": 2.0,
            "exec_imbalance_deriv": imb_deriv,
            "hazard_jump": hazard_jump,
            "cost": cost,
        },
        cache,
    )
    expected_alpha = 1.0 * math.log(1 + abs(llrti_val) ** 2.0) + 2.0 * abs(
        imb_deriv
    )
    direction = -1.0
    expected_scaled = direction * hazard_jump * expected_alpha / (1.0 + cost)
    assert result["alpha"] == pytest.approx(expected_scaled)


def test_latent_liquidity_alpha_node_cost_penalty():
    no_cost = latent_liquidity_alpha_node(
        {
            "llrti": 0.0,
            "hazard_jump": 1.0,
            "exec_imbalance_deriv": 1.0,
            "theta1": 0.0,
            "theta2": 1.0,
            "cost": 0.0,
        }
    )["alpha"]
    with_cost = latent_liquidity_alpha_node(
        {
            "llrti": 0.0,
            "hazard_jump": 1.0,
            "exec_imbalance_deriv": 1.0,
            "theta1": 0.0,
            "theta2": 1.0,
            "cost": 1.0,
        }
    )["alpha"]
    assert with_cost == pytest.approx(no_cost / 2)
