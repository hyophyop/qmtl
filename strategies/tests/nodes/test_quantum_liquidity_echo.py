import math
from qmtl.sdk.cache_view import CacheView
from qmtl.sdk.node import Node

from strategies.nodes.indicators.quantum_liquidity_echo import quantum_liquidity_echo_node


def test_echo_amplitude_estimation():
    data = {
        "alphas": [1.0, 2.0, 3.0],
        "delta_t": 1.0,
        "tau": 2.0,
        "sigma": 1.0,
        "threshold": 100.0,
    }
    out = quantum_liquidity_echo_node(data)
    expected = sum(
        alpha * math.exp(-k * data["delta_t"] / data["tau"])
        for k, alpha in enumerate(data["alphas"], start=1)
    )
    assert math.isclose(out["echo_amplitude"], expected)


def test_threshold_detection():
    data = {
        "alphas": [5.0],
        "delta_t": 1.0,
        "tau": 1.0,
        "sigma": 0.5,
        "threshold": 5.0,
    }
    out = quantum_liquidity_echo_node(data)
    assert out["action"] == -1


def test_non_linear_strategy_response():
    base = {
        "alphas": [0.5],
        "delta_t": 1.0,
        "tau": 1.0,
        "sigma": 1.0,
        "threshold": 0.05,
    }
    doubled = {
        "alphas": [1.0],
        "delta_t": 1.0,
        "tau": 1.0,
        "sigma": 1.0,
        "threshold": 0.05,
    }
    out_base = quantum_liquidity_echo_node(base)
    out_doubled = quantum_liquidity_echo_node(doubled)
    assert out_base["action"] == 0
    assert out_doubled["action"] == -1
    assert math.isclose(out_doubled["qe"], out_base["qe"] * 4)


def test_cacheview_history_lookup():
    def _dummy(view: CacheView):  # pragma: no cover - placeholder
        return None

    src = Node(compute_fn=_dummy, name="src", interval=1)
    view = CacheView({src.node_id: {1: [(0, 1.0), (1, 2.0), (2, 3.0)]}})
    data = {
        "source": src,
        "delta_t": 1.0,
        "tau": 2.0,
        "sigma": 1.0,
        "threshold": 100.0,
    }
    out = quantum_liquidity_echo_node(data, view)
    expected = sum(
        alpha * math.exp(-k * data["delta_t"] / data["tau"])
        for k, alpha in enumerate([1.0, 2.0, 3.0], start=1)
    )
    assert math.isclose(out["echo_amplitude"], expected)
