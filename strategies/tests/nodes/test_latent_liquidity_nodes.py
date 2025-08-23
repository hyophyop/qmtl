import math
import pytest

from strategies.nodes.indicators.llrti import llrti_node
from strategies.nodes.indicators.latent_liquidity_alpha import (
    latent_liquidity_alpha_node,
)
from qmtl.transforms import execution_imbalance_node, rate_of_change, llrti
from qmtl.sdk.node import SourceNode
from qmtl.sdk.cache_view import CacheView


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
    expected = llrti([1.0, -0.5], 0.02, 2.0, 0.01)
    assert result["llrti"] == pytest.approx(expected)
    ns = cache["latent_liquidity"]
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
    expected = llrti([1.0], 0.005, 1.0, 0.01)
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
    expected = llrti([1.0], 0.01, 1.0, 0.01)
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

    buy = SourceNode(interval="1s", period=2, config={"id": "buy"})
    sell = SourceNode(interval="1s", period=2, config={"id": "sell"})
    ei_node = execution_imbalance_node(buy, sell)
    data0 = {buy.node_id: {1: [(0, 60.0)]}, sell.node_id: {1: [(0, 40.0)]}}
    val0 = ei_node.compute_fn(CacheView(data0))
    data1 = {
        buy.node_id: {1: [(0, 60.0), (1, 66.0)]},
        sell.node_id: {1: [(0, 40.0), (1, 34.0)]},
    }
    val1 = ei_node.compute_fn(CacheView(data1))
    roc_node = rate_of_change(ei_node, period=2)
    imb_deriv = roc_node.compute_fn(
        CacheView({ei_node.node_id: {1: [(0, val0), (1, val1)]}})
    )

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
    ns = cache["latent_liquidity"]
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

    buy = SourceNode(interval="1s", period=2, config={"id": "buy"})
    sell = SourceNode(interval="1s", period=2, config={"id": "sell"})
    ei_node = execution_imbalance_node(buy, sell)
    data0 = {buy.node_id: {1: [(0, 60.0)]}, sell.node_id: {1: [(0, 40.0)]}}
    val0 = ei_node.compute_fn(CacheView(data0))
    data1 = {
        buy.node_id: {1: [(0, 60.0), (1, 40.0)]},
        sell.node_id: {1: [(0, 40.0), (1, 60.0)]},
    }
    val1 = ei_node.compute_fn(CacheView(data1))
    roc_node = rate_of_change(ei_node, period=2)
    imb_deriv = roc_node.compute_fn(
        CacheView({ei_node.node_id: {1: [(0, val0), (1, val1)]}})
    )

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
