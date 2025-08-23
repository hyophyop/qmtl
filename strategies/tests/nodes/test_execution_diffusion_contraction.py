import sys
import types

sys.modules.setdefault("qmtl.sdk.cache_view", types.SimpleNamespace(CacheView=object))

trans_mod = types.ModuleType("qmtl.transforms.execution_diffusion_contraction")


def _hp(x, eta):  # pragma: no cover - simple stub
    return 0.5


def _ej(gaps, cum_depth, q, zeta=0.5):  # pragma: no cover - simple stub
    return gaps[0] if gaps else 0.0


def _es(prob, jump):  # pragma: no cover - simple stub
    return prob * jump


trans_mod.hazard_probability = _hp
trans_mod.expected_jump = _ej
trans_mod.edch_side = _es

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
