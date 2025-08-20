import math
import pytest

from strategies.nodes.indicators.tactical_liquidity_bifurcation import (
    tactical_liquidity_bifurcation_node,
)


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
