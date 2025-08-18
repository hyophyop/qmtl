import math

import pytest

from strategies.nodes.indicators import gap_amplification
from strategies.nodes.indicators.gap_amplification import gap_amplification_node


def test_gap_amplification_node_computes_expected_features():
    data = {
        "ask_gaps": [1.0, 2.0],
        "ask_depths": [10.0, 20.0],
        "bid_gaps": [1.0, 2.0],
        "bid_depths": [5.0, 20.0],
        "lambda": 0.0,
        "ofi": 0.0,
        "spread_z": 0.0,
        "eta": (0.0, 0.0, 0.0),
    }
    result = gap_amplification_node(data)

    gas_ask = 1.0 / 10.0 + 2.0 / 20.0
    gas_bid = 1.0 / 5.0 + 2.0 / 20.0
    hazard = 1.0 / (1.0 + math.exp(0.0))

    assert result["gas_ask"] == pytest.approx(gas_ask)
    assert result["gas_bid"] == pytest.approx(gas_bid)
    assert result["hazard"] == pytest.approx(hazard)
    assert result["gati_ask"] == pytest.approx(gas_ask * hazard)
    assert result["gati_bid"] == pytest.approx(gas_bid * hazard)
    assert result["alpha"] == pytest.approx((gas_bid - gas_ask) * hazard)


def test_gap_amplification_node_handles_zero_depth():
    data = {
        "ask_gaps": [1.0],
        "ask_depths": [0.0],
        "bid_gaps": [],
        "bid_depths": [],
    }
    result = gap_amplification_node(data)

    assert result["gas_ask"] == 0.0
    assert result["gas_bid"] == 0.0
    assert result["hazard"] == pytest.approx(0.5)
    assert result["gati_ask"] == 0.0
    assert result["gati_bid"] == 0.0
    assert result["alpha"] == 0.0


def test_gap_amplification_node_calls_qmtl_functions(monkeypatch):
    calls = {"gas": [], "hazard": []}

    def fake_gas(gaps, depths, lam, eps=1e-9):  # pragma: no cover - simple spy
        calls["gas"].append((gaps, depths, lam))
        if gaps == [1.0, 2.0] and depths == [10.0, 20.0]:
            return 0.3
        if gaps == [1.0, 2.0] and depths == [5.0, 20.0]:
            return 0.4
        return 0.0

    def fake_hazard(ofi, spread_z, eta0, eta1, eta2):  # pragma: no cover - simple spy
        calls["hazard"].append((ofi, spread_z, eta0, eta1, eta2))
        return 0.25

    monkeypatch.setattr(gap_amplification, "_gas", fake_gas)
    monkeypatch.setattr(gap_amplification, "_hazard", fake_hazard)

    data = {
        "ask_gaps": [1.0, 2.0],
        "ask_depths": [10.0, 20.0],
        "bid_gaps": [1.0, 2.0],
        "bid_depths": [5.0, 20.0],
        "lambda": 0.3,
        "ofi": 1.0,
        "spread_z": -1.0,
        "eta": (0.1, 0.2, 0.3),
    }

    result = gap_amplification.gap_amplification_node(data)

    assert calls["gas"] == [
        ([1.0, 2.0], [10.0, 20.0], 0.3),
        ([1.0, 2.0], [5.0, 20.0], 0.3),
    ]
    assert calls["hazard"] == [(1.0, -1.0, 0.1, 0.2, 0.3)]
    assert result["gas_ask"] == 0.3
    assert result["gas_bid"] == 0.4
    assert result["hazard"] == 0.25
    assert result["gati_ask"] == pytest.approx(0.3 * 0.25)
    assert result["gati_bid"] == pytest.approx(0.4 * 0.25)
    assert result["alpha"] == pytest.approx((0.4 - 0.3) * 0.25)
