import math
import pytest

from strategies.nodes.indicators.impact import impact_node
from strategies.nodes.indicators.non_linear_alpha import non_linear_alpha_node
from qmtl.indicators import volatility_node
from qmtl.transforms import order_book_imbalance_node, rate_of_change
from qmtl.sdk.cache_view import CacheView
from qmtl.sdk.node import SourceNode


def test_impact_node_computes_expected_value():
    data = {"volume": 100, "avg_volume": 400, "depth": 10, "beta": 0.5}
    result = impact_node(data)
    expected = math.sqrt(100 / 400) / (10 ** 0.5)
    assert result["impact"] == pytest.approx(expected)


def test_non_linear_alpha_node_computes_expected_value():
    impact_val = impact_node({"volume": 100, "avg_volume": 400, "depth": 10, "beta": 1.0})["impact"]

    price_src = SourceNode(interval="1s", period=5, config={"id": "price"})
    vol_node = volatility_node(price_src, window=2)
    price_data = {price_src.node_id: {1: [(0, 1.0), (1, 2.0), (2, 1.0)]}}
    volatility_val = vol_node.compute_fn(CacheView(price_data))

    bid = SourceNode(interval="1s", period=2, config={"id": "bid"})
    ask = SourceNode(interval="1s", period=2, config={"id": "ask"})
    obi_node = order_book_imbalance_node(bid, ask)
    data0 = {bid.node_id: {1: [(0, 75.0)]}, ask.node_id: {1: [(0, 25.0)]}}
    val0 = obi_node.compute_fn(CacheView(data0))
    data1 = {bid.node_id: {1: [(0, 75.0), (1, 77.5)]}, ask.node_id: {1: [(0, 25.0), (1, 22.5)]}}
    val1 = obi_node.compute_fn(CacheView(data1))
    roc_node = rate_of_change(obi_node, period=2)
    view = CacheView({obi_node.node_id: {1: [(0, val0), (1, val1)]}})
    obi_deriv = roc_node.compute_fn(view)

    result = non_linear_alpha_node(
        {
            "impact": impact_val,
            "volatility": volatility_val,
            "obi_derivative": obi_deriv,
            "gamma": 1.0,
        }
    )
    expected = math.tanh(1.0 * impact_val * volatility_val) * obi_deriv
    assert result["alpha"] == pytest.approx(expected)
