import importlib.util
import math
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "nodes"
    / "indicators"
    / "resiliency_alpha.py"
)
sys.path.append(str(Path(__file__).resolve().parents[3] / "qmtl"))
spec = importlib.util.spec_from_file_location(
    "resiliency_alpha", MODULE_PATH
)
ra = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(ra)  # type: ignore[attr-defined]
resiliency_alpha_node = ra.resiliency_alpha_node
CACHE = ra.CACHE


def test_input_cache_reuse():
    CACHE.invalidate()
    base = {
        "timestamp": 1,
        "side": "bid",
        "level": 0,
        "volume": 100.0,
        "avg_volume": 20.0,
        "depth": 5.0,
        "volatility": 0.2,
        "obi_derivative": 0.1,
        "beta": 1.5,
        "gamma": 2.0,
    }
    out1 = resiliency_alpha_node(base)

    reused = {
        "timestamp": 1,
        "side": "bid",
        "level": 0,
        "obi_derivative": 0.1,
        "beta": 1.5,
        "gamma": 2.0,
    }
    out2 = resiliency_alpha_node(reused)

    assert out1 == out2
    for metric in ("volume", "avg_volume", "depth", "volatility"):
        assert CACHE.get(1, "bid", 0, metric) is not None


def test_alpha_tanh_behavior():
    CACHE.invalidate()
    params = {
        "timestamp": 2,
        "side": "ask",
        "level": 1,
        "volume": 400.0,
        "avg_volume": 25.0,
        "depth": 2.0,
        "volatility": 3.0,
        "obi_derivative": 0.5,
        "beta": 1.0,
        "gamma": 10.0,
    }
    out = resiliency_alpha_node(params)
    impact_val = ra.impact(400.0, 25.0, 2.0, 1.0)
    expected = math.tanh(10.0 * impact_val * 3.0) * 0.5
    assert out["alpha"] == expected
    assert abs(out["alpha"]) <= 0.5

    CACHE.invalidate()
    params_neg = {
        **params,
        "timestamp": 3,
        "volatility": -3.0,
    }
    out_neg = resiliency_alpha_node(params_neg)
    expected_neg = math.tanh(10.0 * impact_val * -3.0) * 0.5
    assert out_neg["alpha"] == expected_neg
    assert abs(out_neg["alpha"]) <= 0.5 and out_neg["alpha"] < 0
