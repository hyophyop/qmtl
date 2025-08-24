import sys
import types
import importlib.util
from pathlib import Path

sys.modules.setdefault("qmtl.sdk.cache_view", types.SimpleNamespace(CacheView=object))

trans_mod = types.ModuleType("qmtl.transforms.execution_diffusion_contraction")


def _hp(x, eta):  # pragma: no cover - simple stub
    return 0.5


def _ej(gaps, cum_depth, q, zeta=0.5):  # pragma: no cover - simple stub
    return gaps[0] if gaps else 0.0


def _es(prob, jump):  # pragma: no cover - simple stub
    return prob * jump

# Load real transform functions for concentration and depth utilities
spec = importlib.util.spec_from_file_location(
    "_real_exec_diff",
    Path(__file__).resolve().parents[3]
    / "qmtl"
    / "qmtl"
    / "transforms"
    / "execution_diffusion_contraction.py",
)
real_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(real_mod)

trans_mod.hazard_probability = _hp
trans_mod.expected_jump = _ej
trans_mod.edch_side = _es
trans_mod.concentration_scores = real_mod.concentration_scores
trans_mod.path_resistance = real_mod.path_resistance
trans_mod.depth_wedge = real_mod.depth_wedge

pkg = types.ModuleType("qmtl.transforms")
pkg.execution_diffusion_contraction = trans_mod
sys.modules.setdefault("qmtl.transforms", pkg)
sys.modules.setdefault(
    "qmtl.transforms.execution_diffusion_contraction", trans_mod
)

import pytest

import strategies.nodes.indicators.execution_diffusion_contraction as edch

from strategies.nodes.indicators.execution_diffusion_contraction import (
    execution_diffusion_contraction_node,
    invalidate_edch_cache,
)

CACHE = edch.CACHE


def test_execution_diffusion_contraction_node():
    invalidate_edch_cache()
    data = {
        "up_prob": 0.6,
        "up_jump": 1.0,
        "down_prob": 0.4,
        "down_jump": 0.5,
    }
    out = execution_diffusion_contraction_node(data)
    assert out["edch_up"] == pytest.approx(0.6)
    assert out["edch_down"] == pytest.approx(0.2)
    assert out["alpha"] == pytest.approx(0.6 - 0.2)


def test_execution_diffusion_contraction_cache(monkeypatch):
    invalidate_edch_cache()

    calls = {"count": 0}
    orig = edch.expected_jump

    def spy(gaps, cum_depth, q, zeta=0.5):
        calls["count"] += 1
        return orig(gaps, cum_depth, q, zeta)

    monkeypatch.setattr(edch, "expected_jump", spy)

    base = {
        "timestamp": 1,
        "up_inputs": [0.1],
        "up_eta": [0.0, 1.0],
        "up_gaps": [1.0, 0.5],
        "up_cum_depth": [0.4, 0.8],
        "up_Q": 0.6,
        "down_inputs": [0.2],
        "down_eta": [0.0, 1.0],
        "down_gaps": [1.0, 0.5],
        "down_cum_depth": [0.4, 0.8],
        "down_Q": 0.6,
    }

    out1 = execution_diffusion_contraction_node(base)
    assert calls["count"] == 2
    assert CACHE.get(1, "up", 0, "jump") is not None

    second = {
        "timestamp": 1,
        "up_inputs": [0.1],
        "up_eta": [0.0, 1.0],
        "up_Q": 0.6,
        "down_inputs": [0.2],
        "down_eta": [0.0, 1.0],
        "down_Q": 0.6,
    }

    out2 = execution_diffusion_contraction_node(second)
    assert calls["count"] == 2
    assert out1 == out2

    invalidate_edch_cache(jumps=True, cum_depth=False, gaps=False)
    assert CACHE.get(1, "up", 0, "jump") is None

    out3 = execution_diffusion_contraction_node(second)
    assert calls["count"] == 4
    assert out3 == out1
    assert CACHE.get(1, "up", 0, "jump") is not None


def test_edch_raw_inputs_hazard_integration(monkeypatch):
    captured: dict[str, list[float]] = {}

    def spy(x, eta):  # pragma: no cover - capture inputs
        captured["x"] = list(x)
        return 0.5

    monkeypatch.setattr(edch, "hazard_probability", spy)

    data = {
        "bins": 2,
        "up_exec_prices_ticks": [1.0, 1.0, 2.0],
        "up_exec_sizes": [1.0, 1.0, 1.0],
        "up_lambda": [1.0, 2.0],
        "up_depth": [1.0, 1.0],
        "down_depth": [2.0, 1.0],
        "bid_vol_prev": 1.0,
        "bid_vol_curr": 2.0,
        "ask_vol_prev": 2.0,
        "ask_vol_curr": 1.0,
        "spread": 1.0,
        "spread_mean": 1.0,
        "spread_std": 1.0,
        "microprice_prev": 100.0,
        "microprice_curr": 100.5,
        "up_eta": [0.0] * 8,
        "up_jump": 1.0,
    }

    _ = edch._edch(data, "up")
    features = captured["x"]

    ent, hhi, fano = real_mod.concentration_scores(
        [1.0, 1.0, 2.0], [1.0, 1.0, 1.0], 2
    )
    conc = ent + hhi - fano
    res = real_mod.path_resistance([1.0, 1.0])
    wedge = real_mod.depth_wedge([1.0, 1.0], [2.0, 1.0])

    expected = [conc, 1.0, res, 2.0, 0.0, 0.5, wedge]
    assert features == pytest.approx(expected)
