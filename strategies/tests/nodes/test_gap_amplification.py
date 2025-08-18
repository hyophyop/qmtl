import math
import pytest

from strategies.nodes.indicators.gap_amplification import gap_amplification_node


def test_gap_amplification_node_computes_alpha():
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
    expected_alpha = (gas_bid - gas_ask) * hazard
    assert result["alpha"] == pytest.approx(expected_alpha)
    assert result["gati_ask"] == pytest.approx(gas_ask * hazard)
    assert result["gati_bid"] == pytest.approx(gas_bid * hazard)


def test_gap_amplification_node_handles_zero_depth():
    data = {
        "ask_gaps": [1.0],
        "ask_depths": [0.0],
        "bid_gaps": [],
        "bid_depths": [],
    }
    result = gap_amplification_node(data)
    assert result["gati_ask"] == 0.0
    assert result["alpha"] == 0.0
