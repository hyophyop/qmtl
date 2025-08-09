import math
import pytest

from strategies.nodes.indicators.impact import impact_node
from strategies.nodes.indicators.non_linear_alpha import non_linear_alpha_node


def test_impact_node_computes_expected_value():
    data = {"volume": 100, "avg_volume": 400, "depth": 10, "beta": 0.5}
    result = impact_node(data)
    expected = math.sqrt(100 / 400) / (10 ** 0.5)
    assert result["impact"] == pytest.approx(expected)


def test_non_linear_alpha_node_computes_expected_value():
    data = {"impact": 0.5, "volatility": 2.0, "obi_derivative": 0.1, "gamma": 1.0}
    result = non_linear_alpha_node(data)
    expected = math.tanh(1.0 * 0.5 * 2.0) * 0.1
    assert result["alpha"] == pytest.approx(expected)
