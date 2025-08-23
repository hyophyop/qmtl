import pytest

from qmtl.sdk.cache_view import CacheView
from qmtl.indicators.gap_amplification_alpha import gap_amplification_node
from qmtl.transforms.gap_amplification import gap_over_depth_sum, hazard_probability


def test_alpha_calculation_from_precomputed_inputs():
    data = {"gas_ask": 0.3, "gas_bid": 0.4, "hazard": 0.25}
    result = gap_amplification_node(data)
    assert result["gati_ask"] == pytest.approx(0.3 * 0.25)
    assert result["gati_bid"] == pytest.approx(0.4 * 0.25)
    assert result["alpha"] == pytest.approx((0.4 - 0.3) * 0.25)


def test_hazard_and_alpha_computation_from_raw_inputs():
    data = {
        "ask_gaps": [1.0, 2.0],
        "ask_depths": [10.0, 20.0],
        "bid_gaps": [1.0, 2.0],
        "bid_depths": [5.0, 20.0],
        "lambda": 0.0,
        "ofi": 1.0,
        "spread_z": -1.0,
        "eta": (0.1, 0.2, 0.3),
    }
    result = gap_amplification_node(data)
    gas_ask = gap_over_depth_sum(data["ask_gaps"], data["ask_depths"], data["lambda"])
    gas_bid = gap_over_depth_sum(data["bid_gaps"], data["bid_depths"], data["lambda"])
    hazard = hazard_probability(data["ofi"], data["spread_z"], *data["eta"])
    assert result["gas_ask"] == pytest.approx(gas_ask)
    assert result["gas_bid"] == pytest.approx(gas_bid)
    assert result["hazard"] == pytest.approx(hazard)
    assert result["alpha"] == pytest.approx((gas_bid - gas_ask) * hazard)


def test_cache_view_integration_for_input_reuse():
    time_idx = 0
    lam = 0.0
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
    assert cache_data[time_idx]["ask"][0]["gas"] == pytest.approx(gas_ask)
    assert cache_data[time_idx]["hazard"][0]["hazard"] == pytest.approx(hazard)
    assert result["alpha"] == pytest.approx((gas_bid - gas_ask) * hazard)
