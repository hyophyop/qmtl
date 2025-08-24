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


def test_invalidate_edch_cache_behavior():
    """Ensure cache entries are selectively and fully invalidated."""
    invalidate_edch_cache()

    CACHE.set(1, "up", 0, "jump", 1.0)
    CACHE.set(1, "up", 0, "gaps", [1.0])
    CACHE.set(1, "up", 0, "cum_depth", [0.5])
    CACHE.set(2, "down", 1, "jump", 2.0)

    invalidate_edch_cache(
        time=1, side="up", jumps=False, gaps=True, cum_depth=False
    )
    assert CACHE.get(1, "up", 0, "gaps") is None
    assert CACHE.get(1, "up", 0, "jump") == 1.0
    assert CACHE.get(1, "up", 0, "cum_depth") == [0.5]
    assert CACHE.get(2, "down", 1, "jump") == 2.0

    invalidate_edch_cache()
    assert CACHE.get(1, "up", 0, "jump") is None
    assert CACHE.get(1, "up", 0, "cum_depth") is None
    assert CACHE.get(2, "down", 1, "jump") is None


def test_concentration_scores_hazard_cache(monkeypatch):
    """Compute EDCH with concentration-score inputs and verify cache hits."""
    import math

    invalidate_edch_cache()

    def concentration_scores(exec_prices_ticks, exec_sizes, bins, eps=1e-12):
        if len(exec_prices_ticks) == 0:
            return 0.0, 0.0, 0.0
        min_p = min(exec_prices_ticks)
        max_p = max(exec_prices_ticks)
        hist = [0.0] * bins
        if max_p - min_p < eps:
            hist[0] = sum(exec_sizes)
        else:
            bin_width = (max_p - min_p) / bins
            for price, size in zip(exec_prices_ticks, exec_sizes):
                idx = min(int((price - min_p) / bin_width), bins - 1)
                hist[idx] += size
        total = sum(hist) + eps
        p = [h / total for h in hist]
        entropy = -sum(pi * math.log(pi + eps) for pi in p if pi > 0)
        hhi = sum(pi * pi for pi in p)
        deltas = [
            abs(exec_prices_ticks[i] - exec_prices_ticks[i - 1])
            for i in range(1, len(exec_prices_ticks))
        ]
        if deltas:
            mean_d = sum(deltas) / len(deltas)
            var_d = sum((d - mean_d) ** 2 for d in deltas) / len(deltas)
            fano = var_d / (mean_d + eps)
        else:
            fano = 0.0
        return entropy, hhi, fano

    def hazard_probability_fn(x, eta):
        if not eta:
            return 0.5
        val = eta[0]
        for coeff, xi in zip(eta[1:], x):
            val += coeff * xi
        return 1.0 / (1.0 + math.exp(-val))

    def expected_jump_fn(gaps, cum_depth, q, zeta=0.5):
        if not gaps:
            return 0.0
        pj = [1.0 if depth <= q else 0.5 for depth in cum_depth]
        jump = gaps[0]
        for prob, gap in zip(pj[1:], gaps[1:]):
            jump += zeta * prob * gap
        return jump

    calls = {"count": 0}

    def expected_jump_spy(gaps, cum_depth, q, zeta=0.5):
        calls["count"] += 1
        return expected_jump_fn(gaps, cum_depth, q, zeta)

    monkeypatch.setattr(edch, "hazard_probability", hazard_probability_fn)
    monkeypatch.setattr(edch, "expected_jump", expected_jump_spy)
    monkeypatch.setattr(edch, "edch_side", lambda prob, jump: prob * jump)

    up_prices = [1.0, 2.0, 3.0]
    up_sizes = [1.0, 1.0, 1.0]
    up_scores = concentration_scores(up_prices, up_sizes, bins=3)

    down_prices = [1.0, 1.5, 1.7]
    down_sizes = [1.0, 2.0, 1.0]
    down_scores = concentration_scores(down_prices, down_sizes, bins=3)

    base = {
        "timestamp": 1,
        "up_inputs": list(up_scores),
        "up_eta": [0.2, -0.1, 0.05, 0.1],
        "up_gaps": [0.5, 0.2],
        "up_cum_depth": [0.3, 0.8],
        "up_Q": 0.6,
        "down_inputs": list(down_scores),
        "down_eta": [-0.3, 0.2, -0.1, 0.2],
        "down_gaps": [0.4, 0.3],
        "down_cum_depth": [0.2, 0.7],
        "down_Q": 0.5,
    }

    out1 = execution_diffusion_contraction_node(base)

    exp_up = hazard_probability_fn(base["up_inputs"], base["up_eta"]) * expected_jump_fn(
        base["up_gaps"], base["up_cum_depth"], base["up_Q"]
    )
    exp_down = hazard_probability_fn(base["down_inputs"], base["down_eta"]) * expected_jump_fn(
        base["down_gaps"], base["down_cum_depth"], base["down_Q"]
    )

    assert calls["count"] == 2
    assert out1["edch_up"] == pytest.approx(exp_up)
    assert out1["edch_down"] == pytest.approx(exp_down)
    assert out1["alpha"] == pytest.approx(exp_up - exp_down)
    assert out1["alpha"] > 0

    partial = {
        "timestamp": 1,
        "up_inputs": list(up_scores),
        "up_eta": [0.2, -0.1, 0.05, 0.1],
        "up_Q": 0.6,
        "down_inputs": list(down_scores),
        "down_eta": [-0.3, 0.2, -0.1, 0.2],
        "down_Q": 0.5,
    }

    out2 = execution_diffusion_contraction_node(partial)
    assert calls["count"] == 2
    assert out2 == out1

    invalidate_edch_cache()
    out3 = execution_diffusion_contraction_node(base)
    assert calls["count"] == 4
    assert out3 == out1
