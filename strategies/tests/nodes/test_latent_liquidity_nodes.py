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
        },
        cache,
    )
    expected = _llrti([1.0, -0.5], 0.02, 2.0, 0.01)
    assert result["llrti"] == pytest.approx(expected)
    expected_hazard = 1.0 / (1.0 + math.exp(-expected))
    assert result["hazard"] == pytest.approx(expected_hazard)
    assert result["cost"] == pytest.approx(0.011)
    ns = cache[CACHE_NS]
    assert ns["depth_changes"][(0, "buy", 0)] == 1.0
    assert ns["depth_changes"][(1, "buy", 0)] == -0.5
    assert ns["llrti_hazard"][(1, "buy", 0)] == pytest.approx(expected_hazard)


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
        },
        cache,
    )
    llrti_val = llrti_res["llrti"]
    hazard = llrti_res["hazard"]
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
            "hazard": hazard,
            "cost": cost,
        },
        cache,
    )
    expected_alpha = 1.0 * math.log(1 + abs(llrti_val) ** 2.0) + 2.0 * imb_deriv
    expected_scaled = hazard * expected_alpha / (1.0 + cost)
    assert result["alpha"] == pytest.approx(expected_scaled)
    ns = cache[CACHE_NS]
    assert ns["exec_delta"][(1, "buy", 0)] == imb_deriv
    assert ns["llrti_hazard"][(1, "buy", 0)] == pytest.approx(hazard)


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
        },
        cache,
    )
    llrti_val = llrti_res["llrti"]
    hazard = llrti_res["hazard"]
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
            "hazard": hazard,
            "cost": cost,
        },
        cache,
    )
    expected_alpha = 1.0 * math.log(1 + abs(llrti_val) ** 2.0) + 2.0 * imb_deriv
    expected_scaled = hazard * expected_alpha / (1.0 + cost)
    assert result["alpha"] == pytest.approx(expected_scaled)
