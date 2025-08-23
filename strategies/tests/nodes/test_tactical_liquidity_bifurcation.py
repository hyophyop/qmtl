import importlib.util
import math
from pathlib import Path
import pytest

import sys
import types

fake_tlb = types.SimpleNamespace(
    bifurcation_hazard=lambda z, beta: 0.0,
    direction_signal=lambda side, z, eta: 0.0,
    tlbh_alpha=lambda h, g, pi, cost, gamma, tau, phi: max(h**gamma - cost, 0.0)
    * g
    * pi
    * math.exp(-tau),
)
fake_occ = types.SimpleNamespace(
    execution_cost=lambda spread, taker_fee, impact: spread + taker_fee + impact,
)
sys.modules[
    "qmtl.transforms.tactical_liquidity_bifurcation"
] = fake_tlb
sys.modules[
    "qmtl.transforms.order_book_clustering_collapse"
] = fake_occ

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "nodes"
    / "indicators"
    / "tactical_liquidity_bifurcation.py"
)
spec = importlib.util.spec_from_file_location("tlb", MODULE_PATH)
tlb = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(tlb)
tactical_liquidity_bifurcation_node = tlb.tactical_liquidity_bifurcation_node


def test_tactical_liquidity_bifurcation_node_basic():
    data = {
        "hazard_ask": 0.4,
        "hazard_bid": 0.6,
        "g_ask": 0.3,
        "g_bid": -0.2,
        "pi": 0.8,
        "cost": 0.1,
        "gamma": 2.0,
        "tau": 0.1,
        "phi": 1.0,
    }
    result = tactical_liquidity_bifurcation_node(data)
    alpha_ask = max(0.4 ** 2 - 0.1, 0.0) * 0.3
    alpha_bid = max(0.6 ** 2 - 0.1, 0.0) * -0.2
    expected = (alpha_ask + alpha_bid) * 0.8 * math.exp(-0.1)
    assert result["alpha"] == pytest.approx(expected)


def test_tactical_liquidity_bifurcation_cache_roundtrip():
    first = tactical_liquidity_bifurcation_node(
        {
            "timestamp": 123,
            "hazard_ask": 0.1,
            "hazard_bid": 0.2,
            "g_ask": 0.3,
            "g_bid": -0.4,
            "pi": 0.9,
            "cost": 0.05,
        }
    )
    second = tactical_liquidity_bifurcation_node({"timestamp": 123, "pi": 0.9})
    assert second == first


def test_tactical_liquidity_bifurcation_cache_toggle():
    tactical_liquidity_bifurcation_node(
        {
            "timestamp": 999,
            "hazard_ask": 0.2,
            "hazard_bid": 0.2,
            "g_ask": 0.1,
            "g_bid": -0.1,
            "pi": 0.5,
            "cost": 0.3,
        }
    )
    result = tactical_liquidity_bifurcation_node({"timestamp": 999}, use_cache=False)
    assert result["hazard_ask"] == 0.0
    assert result["g_ask"] == 0.0
    assert result["cost"] == 0.0
