import math
import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.append(str(ROOT / "qmtl"))

import strategies.nodes.indicators.order_book_clustering_collapse as obcc
from strategies.nodes.indicators.order_book_clustering_collapse import (
    order_book_clustering_collapse_node,
)
from qmtl.transforms.order_book_clustering_collapse import (
    hazard_probability,
    direction_gating,
    execution_cost,
)
from qmtl.sdk.cache_view import CacheView
from qmtl.sdk.node import Node


def test_obcc_node_computes_alpha():
    data = {
        "hazard_ask": 0.4,
        "hazard_bid": 0.6,
        "g_ask": 0.2,
        "g_bid": -0.3,
        "pi": 0.5,
        "cost": 0.1,
        "gamma": 2.0,
        "tau": 0.1,
        "phi": 1.0,
    }
    result = order_book_clustering_collapse_node(data)

    alpha_ask = max(0.4 ** 2 - 0.1, 0.0) * 0.2
    alpha_bid = max(0.6 ** 2 - 0.1, 0.0) * -0.3
    expected = (alpha_ask + alpha_bid) * 0.5 * math.exp(-0.1)
    assert result["alpha"] == pytest.approx(expected)


def test_obcc_node_computes_features_when_missing():
    beta = (0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    eta = (0.0, 1.0, 0.0, 0.0)
    data = {
        "beta": beta,
        "eta": eta,
        "ask_z_C": 0.0,
        "ask_z_Cliff": 0.0,
        "ask_z_Gap": 0.0,
        "ask_z_CH": 0.0,
        "ask_z_RL": 0.0,
        "ask_z_Shield": 0.0,
        "ask_z_QDT_inv": 0.0,
        "bid_z_C": -1.0,
        "bid_z_Cliff": 0.0,
        "bid_z_Gap": 0.0,
        "bid_z_CH": 0.0,
        "bid_z_RL": 0.0,
        "bid_z_Shield": 0.0,
        "bid_z_QDT_inv": 0.0,
        "ask_z_OFI": 1.0,
        "ask_z_MicroSlope": 0.0,
        "ask_z_AggFlow": 0.0,
        "bid_z_OFI": 0.0,
        "bid_z_MicroSlope": 0.0,
        "bid_z_AggFlow": 0.0,
        "gamma": 1.0,
        "tau": 0.0,
    }
    result = obcc.order_book_clustering_collapse_node(data)

    hazard_ask = hazard_probability(
        {"C": 0.0, "Cliff": 0.0, "Gap": 0.0, "CH": 0.0, "RL": 0.0, "Shield": 0.0, "QDT_inv": 0.0},
        beta,
    )
    hazard_bid = hazard_probability(
        {"C": -1.0, "Cliff": 0.0, "Gap": 0.0, "CH": 0.0, "RL": 0.0, "Shield": 0.0, "QDT_inv": 0.0},
        beta,
    )
    g_ask = direction_gating(
        +1,
        {"OFI": 1.0, "MicroSlope": 0.0, "AggFlow": 0.0},
        eta,
    )
    g_bid = direction_gating(
        -1,
        {"OFI": 0.0, "MicroSlope": 0.0, "AggFlow": 0.0},
        eta,
    )

    assert result["hazard_ask"] == pytest.approx(hazard_ask)
    assert result["hazard_bid"] == pytest.approx(hazard_bid)
    assert result["g_ask"] == pytest.approx(g_ask)
    assert result["g_bid"] == pytest.approx(g_bid)
    expected_cost = execution_cost(0.0, 0.0, 0.0)
    assert result["cost"] == pytest.approx(expected_cost)
    expected = (hazard_ask * g_ask + hazard_bid * g_bid)
    assert result["alpha"] == pytest.approx(expected)


def test_obcc_node_calls_qmtl_functions(monkeypatch):
    calls = {"hazard": 0, "direction": 0, "cost": 0}

    def fake_hazard(z, beta):
        calls["hazard"] += 1
        return 0.0

    def fake_direction(side, z, eta):
        calls["direction"] += 1
        return 0.0

    def fake_cost(spread, taker_fee, impact):
        calls["cost"] += 1
        return 0.0

    monkeypatch.setattr(obcc, "_hazard", fake_hazard)
    monkeypatch.setattr(obcc, "_direction", fake_direction)
    monkeypatch.setattr(obcc, "_cost", fake_cost)

    data = {
        "ask_z_C": 0.0,
        "ask_z_Cliff": 0.0,
        "ask_z_Gap": 0.0,
        "ask_z_CH": 0.0,
        "ask_z_RL": 0.0,
        "ask_z_Shield": 0.0,
        "ask_z_QDT_inv": 0.0,
        "bid_z_C": 0.0,
        "bid_z_Cliff": 0.0,
        "bid_z_Gap": 0.0,
        "bid_z_CH": 0.0,
        "bid_z_RL": 0.0,
        "bid_z_Shield": 0.0,
        "bid_z_QDT_inv": 0.0,
        "ask_z_OFI": 0.0,
        "ask_z_MicroSlope": 0.0,
        "ask_z_AggFlow": 0.0,
        "bid_z_OFI": 0.0,
        "bid_z_MicroSlope": 0.0,
        "bid_z_AggFlow": 0.0,
        "spread": 0.0,
        "taker_fee": 0.0,
        "impact": 0.0,
    }
    obcc.order_book_clustering_collapse_node(data)

    assert calls["hazard"] == 2
    assert calls["direction"] == 2
    assert calls["cost"] == 1


def test_obcc_uses_cached_values(monkeypatch):
    calls = {"hazard": 0, "direction": 0}

    def fake_hazard(z, beta):
        calls["hazard"] += 1
        return 0.1

    def fake_direction(side, z, eta):
        calls["direction"] += 1
        return 0.05

    monkeypatch.setattr(obcc, "_hazard", fake_hazard)
    monkeypatch.setattr(obcc, "_direction", fake_direction)

    node = Node(name="cache", interval=1, compute_fn=lambda v: None)
    view = CacheView(
        {
            node.node_id: {
                node.interval: [
                    (1, {"hazard_ask": 0.4, "hazard_bid": 0.6, "g_ask": 0.2, "g_bid": -0.3})
                ]
            }
        }
    )

    result = obcc.order_book_clustering_collapse_node(
        {"cache_node": node, "time": 1, "pi": 1.0, "cost": 0.0}, view
    )

    assert result["hazard_ask"] == pytest.approx(0.4)
    assert result["g_bid"] == pytest.approx(-0.3)
    assert calls["hazard"] == 0
    assert calls["direction"] == 0


def test_obcc_cache_miss_triggers_recompute(monkeypatch):
    calls = {"hazard": 0, "direction": 0}

    def fake_hazard(z, beta):
        calls["hazard"] += 1
        return 0.1

    def fake_direction(side, z, eta):
        calls["direction"] += 1
        return 0.05 if side == 1 else -0.05

    monkeypatch.setattr(obcc, "_hazard", fake_hazard)
    monkeypatch.setattr(obcc, "_direction", fake_direction)

    node = Node(name="cache", interval=1, compute_fn=lambda v: None)
    view = CacheView({node.node_id: {node.interval: []}})

    data = {
        "cache_node": node,
        "time": 1,
        "beta": (0.0,) * 8,
        "eta": (0.0,) * 4,
        "ask_z_C": 0.0,
        "ask_z_Cliff": 0.0,
        "ask_z_Gap": 0.0,
        "ask_z_CH": 0.0,
        "ask_z_RL": 0.0,
        "ask_z_Shield": 0.0,
        "ask_z_QDT_inv": 0.0,
        "bid_z_C": 0.0,
        "bid_z_Cliff": 0.0,
        "bid_z_Gap": 0.0,
        "bid_z_CH": 0.0,
        "bid_z_RL": 0.0,
        "bid_z_Shield": 0.0,
        "bid_z_QDT_inv": 0.0,
        "ask_z_OFI": 0.0,
        "ask_z_MicroSlope": 0.0,
        "ask_z_AggFlow": 0.0,
        "bid_z_OFI": 0.0,
        "bid_z_MicroSlope": 0.0,
        "bid_z_AggFlow": 0.0,
        "tau": 0.0,
        "gamma": 1.0,
        "pi": 1.0,
        "cost": 0.0,
    }

    obcc.order_book_clustering_collapse_node(data, view)

    assert calls["hazard"] == 2
    assert calls["direction"] == 2

