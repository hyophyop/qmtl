import importlib.util
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
