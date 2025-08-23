import importlib
import math
import sys
import types
from pathlib import Path

try:  # pragma: no cover - prefer installed qmtl
    from qmtl.sdk.cache_view import CacheView
    from qmtl.sdk.node import Node
except Exception:  # pragma: no cover - fallback to local sources
    sdk_root = Path(__file__).resolve().parents[3] / "qmtl" / "qmtl"
    sys.path.insert(0, str(sdk_root))
    qmtl_pkg = types.ModuleType("qmtl")
    qmtl_pkg.__path__ = []
    sys.modules.setdefault("qmtl", qmtl_pkg)
    sys.modules["qmtl.sdk"] = importlib.import_module("sdk")
    sys.modules["qmtl.sdk.cache_view"] = importlib.import_module("sdk.cache_view")
    sys.modules["qmtl.sdk.node"] = importlib.import_module("sdk.node")
    from qmtl.sdk.cache_view import CacheView
    from qmtl.sdk.node import Node

from strategies.nodes.indicators.quantum_liquidity_echo import quantum_liquidity_echo_node
from strategies.utils.cacheview_helpers import fetch_series


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


def test_cacheview_multi_interval_reads():
    def _dummy(view: CacheView):  # pragma: no cover - placeholder
        return None

    src = Node(compute_fn=_dummy, name="src", interval=1)
    view = CacheView(
        {
            src.node_id: {
                0: {"BUY": {1: {"alpha": 1.0, "beta": 4.0}}},
                1: {"BUY": {1: {"alpha": 2.0, "beta": 5.0}}},
                2: {"BUY": {1: {"alpha": 3.0, "beta": 6.0}}},
            }
        }
    )

    base = {
        "source": src,
        "side": "BUY",
        "level": 1,
        "delta_t": 1.0,
        "tau": 2.0,
        "sigma": 1.0,
        "threshold": 100.0,
    }

    for feature in ("alpha", "beta"):
        data = {**base, "feature": feature}
        out = quantum_liquidity_echo_node(data, view)
        series = fetch_series(view, src, "BUY", 1, feature)
        expected = sum(
            alpha * math.exp(-k * base["delta_t"] / base["tau"])
            for k, alpha in enumerate(series, start=1)
        )
        assert series == [1.0, 2.0, 3.0] if feature == "alpha" else [4.0, 5.0, 6.0]
        assert math.isclose(out["echo_amplitude"], expected)

