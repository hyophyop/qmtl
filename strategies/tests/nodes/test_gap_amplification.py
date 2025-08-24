import pytest
import importlib.util
import sys
import types
from pathlib import Path

# ---------------------------------------------------------------------------
# Minimal qmtl stubs only if real modules unavailable
# ---------------------------------------------------------------------------
try:  # pragma: no cover - use real modules when available
    from qmtl.sdk.cache_view import CacheView
    from qmtl.transforms.gap_amplification import (
        gap_over_depth_sum,
        hazard_probability,
        jump_expectation,
    )
except Exception:  # pragma: no cover - fallback to local sources
    qmtl_pkg = sys.modules.get("qmtl")
    if qmtl_pkg is None:
        qmtl_pkg = types.ModuleType("qmtl")
        sys.modules["qmtl"] = qmtl_pkg

    sdk_module = types.ModuleType("qmtl.sdk")
    metrics_path = Path(__file__).resolve().parents[3] / "qmtl" / "qmtl" / "sdk" / "metrics.py"
    m_spec = importlib.util.spec_from_file_location("qmtl.sdk.metrics", metrics_path)
    metrics_module = importlib.util.module_from_spec(m_spec)
    assert m_spec.loader is not None
    m_spec.loader.exec_module(metrics_module)
    sdk_module.metrics = metrics_module
    sys.modules["qmtl.sdk"] = sdk_module
    sys.modules["qmtl.sdk.metrics"] = metrics_module

    cache_path = Path(__file__).resolve().parents[3] / "qmtl" / "qmtl" / "sdk" / "cache_view.py"
    c_spec = importlib.util.spec_from_file_location("qmtl.sdk.cache_view", cache_path)
    cv_module = importlib.util.module_from_spec(c_spec)
    assert c_spec.loader is not None
    c_spec.loader.exec_module(cv_module)
    sdk_module.cache_view = cv_module
    sys.modules["qmtl.sdk.cache_view"] = cv_module
    qmtl_pkg.sdk = sdk_module

    ga_path = Path(__file__).resolve().parents[3] / "qmtl" / "qmtl" / "transforms" / "gap_amplification.py"
    spec = importlib.util.spec_from_file_location("qmtl.transforms.gap_amplification", ga_path)
    ga_module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(ga_module)
    transforms_pkg = types.ModuleType("qmtl.transforms")
    transforms_pkg.gap_amplification = ga_module
    sys.modules["qmtl.transforms"] = transforms_pkg
    sys.modules["qmtl.transforms.gap_amplification"] = ga_module
    qmtl_pkg.transforms = transforms_pkg

# ensure real modules imported above
import strategies.nodes.indicators.gap_amplification as gap_amplification
from strategies.nodes.indicators.gap_amplification import gap_amplification_node
from strategies.utils.cacheview_helpers import level_series, value_at


def test_gap_amplification_node_computes_alpha():
    ask_gaps = [1.0, 2.0]
    ask_depths = [10.0, 20.0]
    bid_gaps = [1.0, 2.0]
    bid_depths = [5.0, 20.0]
    lam = 0.0
    ofi = 0.0
    spread_z = 0.0
    eta = (0.0, 0.0, 0.0)

    gas_ask = gap_over_depth_sum(ask_gaps, ask_depths, lam)
    gas_bid = gap_over_depth_sum(bid_gaps, bid_depths, lam)
    hazard = hazard_probability(ofi, spread_z, *eta)

    data = {"gas_ask": gas_ask, "gas_bid": gas_bid, "hazard": hazard}
    result = gap_amplification_node(data)

    expected_alpha = (gas_bid - gas_ask) * hazard
    assert result["alpha"] == pytest.approx(expected_alpha)
    assert result["gati_ask"] == pytest.approx(gas_ask * hazard)
    assert result["gati_bid"] == pytest.approx(gas_bid * hazard)
    assert result["alpha"] == pytest.approx((gas_bid - gas_ask) * hazard)
    assert result["jump_ask"] == pytest.approx(1.0)
    assert result["jump_bid"] == pytest.approx(1.0)


def test_gap_amplification_node_handles_zero_depth():
    gas_ask = gap_over_depth_sum([1.0], [0.0], lam=0.5)
    hazard = hazard_probability(0.0, 0.0, 0.0, 0.0, 0.0)
    result = gap_amplification_node({"gas_ask": gas_ask, "gas_bid": 0.0, "hazard": hazard})

    assert result["gati_ask"] == 0.0
    assert result["gati_bid"] == 0.0
    assert result["alpha"] == 0.0


def test_gap_amplification_node_calls_qmtl_functions(monkeypatch):
    calls = {"gas": [], "hazard": [], "jump": []}

    def fake_gas(gaps, depths, lam, eps=1e-9):  # pragma: no cover - simple spy
        calls["gas"].append((gaps, depths, lam))
        if gaps == [1.0, 2.0] and depths == [10.0, 20.0]:
            return 0.3
        if gaps == [1.0, 2.0] and depths == [5.0, 20.0]:
            return 0.4
        return 0.0

    def fake_hazard(ofi, spread_z, eta0, eta1, eta2):  # pragma: no cover - simple spy
        calls["hazard"].append((ofi, spread_z, eta0, eta1, eta2))
        return 0.25

    def fake_jump(gaps, depths, zeta):  # pragma: no cover - simple spy
        calls["jump"].append((gaps, depths, zeta))
        return 1.0

    monkeypatch.setattr(gap_amplification, "_gas", fake_gas)
    monkeypatch.setattr(gap_amplification, "_hazard", fake_hazard)
    monkeypatch.setattr(gap_amplification, "_jump", fake_jump)

    data = {
        "ask_gaps": [1.0, 2.0],
        "ask_depths": [10.0, 20.0],
        "bid_gaps": [1.0, 2.0],
        "bid_depths": [5.0, 20.0],
        "lambda": 0.3,
        "ofi": 1.0,
        "spread_z": -1.0,
        "eta": (0.1, 0.2, 0.3),
    }

    result = gap_amplification.gap_amplification_node(data)

    assert calls["gas"] == [
        ([1.0, 2.0], [10.0, 20.0], 0.3),
        ([1.0, 2.0], [5.0, 20.0], 0.3),
    ]
    assert calls["hazard"] == [(1.0, -1.0, 0.1, 0.2, 0.3)]
    assert calls["jump"] == [
        ([1.0, 2.0], [10.0, 20.0], 0.0),
        ([1.0, 2.0], [5.0, 20.0], 0.0),
    ]
    assert result["gas_ask"] == 0.3
    assert result["gas_bid"] == 0.4
    assert result["hazard"] == 0.25
    assert result["gati_ask"] == pytest.approx(0.3 * 0.25 * 1.0)
    assert result["gati_bid"] == pytest.approx(0.4 * 0.25 * 1.0)
    assert result["alpha"] == pytest.approx((0.4 - 0.3) * 0.25)


def test_gap_amplification_node_cache_hit():
    lam = 0.0
    time_idx = 0
    cache_data = {
        time_idx: {
            "ask": {
                0: {"gap": 1.0, "depth": 10.0},
                1: {"gap": 2.0, "depth": 20.0},
            },
            "bid": {
                0: {"gap": 1.0, "depth": 5.0},
                1: {"gap": 2.0, "depth": 20.0},
            },
            "hazard": {
                0: {
                    "ofi": 0.0,
                    "spread_z": 0.0,
                    "eta0": 0.0,
                    "eta1": 0.0,
                    "eta2": 0.0,
                }
            },
        }
    }
    view = CacheView(cache_data)

    result = gap_amplification_node({"lambda": lam, "time": time_idx}, view)

    gas_ask = gap_over_depth_sum([1.0, 2.0], [10.0, 20.0], lam)
    gas_bid = gap_over_depth_sum([1.0, 2.0], [5.0, 20.0], lam)
    hazard = hazard_probability(0.0, 0.0, 0.0, 0.0, 0.0)

    assert result["gas_ask"] == pytest.approx(gas_ask)
    assert result["gas_bid"] == pytest.approx(gas_bid)
    assert result["hazard"] == pytest.approx(hazard)
    assert level_series(view, time_idx, "ask", "gap") == [1.0, 2.0]
    assert value_at(view, time_idx, "ask", 0, "gas") == pytest.approx(gas_ask)
    assert value_at(view, time_idx, "ask", 0, "jump") == pytest.approx(1.0)
    assert value_at(view, time_idx, "hazard", 0, "hazard") == pytest.approx(hazard)


def test_gap_amplification_node_cache_miss_fallback():
    lam = 0.0
    data = {
        "ask_gaps": [1.0, 2.0],
        "ask_depths": [10.0, 20.0],
        "bid_gaps": [1.0, 2.0],
        "bid_depths": [5.0, 20.0],
        "lambda": lam,
        "ofi": 0.0,
        "spread_z": 0.0,
        "eta": (0.0, 0.0, 0.0),
        "time": 0,
    }
    view = CacheView({})

    result = gap_amplification_node(data, view)

    gas_ask = gap_over_depth_sum(data["ask_gaps"], data["ask_depths"], lam)
    gas_bid = gap_over_depth_sum(data["bid_gaps"], data["bid_depths"], lam)
    hazard = hazard_probability(0.0, 0.0, 0.0, 0.0, 0.0)

    assert result["alpha"] == pytest.approx((gas_bid - gas_ask) * hazard)
    assert value_at(view, 0, "bid", 0, "gas") == pytest.approx(gas_bid)
    assert value_at(view, 0, "bid", 0, "jump") == pytest.approx(1.0)
    assert value_at(view, 0, "hazard", 0, "hazard") == pytest.approx(hazard)


def test_gap_amplification_node_uses_jump_expectation():
    gaps = [1.0, 2.0, 3.0]
    depths = [10.0, 5.0, 5.0]
    lam = 0.0
    zeta = 0.1
    ofi = 0.0
    spread_z = 0.0
    eta = (0.0, 0.0, 0.0)

    gas = gap_over_depth_sum(gaps, depths, lam)
    hazard = hazard_probability(ofi, spread_z, *eta)
    jump = jump_expectation(gaps, depths, zeta)

    data = {
        "ask_gaps": gaps,
        "ask_depths": depths,
        "bid_gaps": gaps,
        "bid_depths": depths,
        "lambda": lam,
        "ofi": ofi,
        "spread_z": spread_z,
        "eta": eta,
        "zeta": zeta,
    }

    result = gap_amplification_node(data)
    assert result["gati_ask"] == pytest.approx(gas * hazard * jump)
