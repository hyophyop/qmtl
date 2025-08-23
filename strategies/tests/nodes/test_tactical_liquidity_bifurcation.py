import math
import pytest

import strategies.nodes.indicators.tactical_liquidity_bifurcation as tlb
from qmtl.transforms.tactical_liquidity_bifurcation import (
    bifurcation_hazard,
    direction_signal as tlb_direction_signal,
)
from qmtl.transforms.order_book_clustering_collapse import execution_cost as occ_execution_cost

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


def test_tlb_node_computes_features_when_missing():
    beta = (0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    eta = (0.0, 1.0, 0.0, 0.0)
    data = {
        "beta": beta,
        "eta": eta,
        "ask_z_SkewDot": 0.0,
        "ask_z_CancelDot": 0.0,
        "ask_z_Gap": 0.0,
        "ask_z_Cliff": 0.0,
        "ask_z_Shield": 0.0,
        "ask_z_QDT_inv": 0.0,
        "ask_z_RequoteLag": 0.0,
        "bid_z_SkewDot": -1.0,
        "bid_z_CancelDot": 0.0,
        "bid_z_Gap": 0.0,
        "bid_z_Cliff": 0.0,
        "bid_z_Shield": 0.0,
        "bid_z_QDT_inv": 0.0,
        "bid_z_RequoteLag": 0.0,
        "ask_z_OFI": 1.0,
        "ask_z_MicroSlope": 0.0,
        "ask_z_AggFlow": 0.0,
        "bid_z_OFI": 0.0,
        "bid_z_MicroSlope": 0.0,
        "bid_z_AggFlow": 0.0,
        "gamma": 1.0,
        "tau": 0.0,
    }
    result = tactical_liquidity_bifurcation_node(data)

    hazard_ask = bifurcation_hazard(
        {
            "SkewDot": 0.0,
            "CancelDot": 0.0,
            "Gap": 0.0,
            "Cliff": 0.0,
            "Shield": 0.0,
            "QDT_inv": 0.0,
            "RequoteLag": 0.0,
        },
        beta,
    )
    hazard_bid = bifurcation_hazard(
        {
            "SkewDot": -1.0,
            "CancelDot": 0.0,
            "Gap": 0.0,
            "Cliff": 0.0,
            "Shield": 0.0,
            "QDT_inv": 0.0,
            "RequoteLag": 0.0,
        },
        beta,
    )
    g_ask = tlb_direction_signal(
        +1,
        {"OFI": 1.0, "MicroSlope": 0.0, "AggFlow": 0.0},
        eta,
    )
    g_bid = tlb_direction_signal(
        -1,
        {"OFI": 0.0, "MicroSlope": 0.0, "AggFlow": 0.0},
        eta,
    )
    expected_cost = occ_execution_cost(0.0, 0.0, 0.0)

    assert result["hazard_ask"] == pytest.approx(hazard_ask)
    assert result["hazard_bid"] == pytest.approx(hazard_bid)
    assert result["g_ask"] == pytest.approx(g_ask)
    assert result["g_bid"] == pytest.approx(g_bid)
    assert result["cost"] == pytest.approx(expected_cost)
    expected = hazard_ask * g_ask + hazard_bid * g_bid
    assert result["alpha"] == pytest.approx(expected)
