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
        },
        cache,
    )
    expected = _llrti([1.0, -0.5], 0.02, 2.0, 0.01)
    assert result["llrti"] == pytest.approx(expected)
    ns = cache[CACHE_NS]
    assert ns["depth_changes"][(0, "buy", 0)] == 1.0
    assert ns["depth_changes"][(1, "buy", 0)] == -0.5


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
    }
    expected = _llrti([1.0], 0.005, 1.0, 0.01)
    assert llrti_node(data, cache)["llrti"] == expected


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
    }
    expected = _llrti([1.0], 0.01, 1.0, 0.01)
    assert llrti_node(data, cache)["llrti"] == expected


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
        },
        cache,
    )
    llrti_val = llrti_res["llrti"]

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
        },
        cache,
    )
    expected_alpha = 1.0 * math.log(1 + abs(llrti_val) ** 2.0) + 2.0 * imb_deriv
    assert result["alpha"] == pytest.approx(expected_alpha)
    ns = cache[CACHE_NS]
    assert ns["exec_delta"][(1, "buy", 0)] == imb_deriv
    assert len(ns["llrti"]) == 2


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
        },
        cache,
    )
    llrti_val = llrti_res["llrti"]

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
        },
        cache,
    )
    expected_alpha = 1.0 * math.log(1 + abs(llrti_val) ** 2.0) + 2.0 * imb_deriv
    assert result["alpha"] == pytest.approx(expected_alpha)
