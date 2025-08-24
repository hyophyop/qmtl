import math

import pytest

from strategies.nodes.indicators.band_conditioned_hazard_moe import (
    band_conditioned_hazard_moe_node,
)


def test_band_conditioned_hazard_moe_momentum():
    data = {
        "pbx": 1.2,
        "hazard_up": 0.6,
        "hazard_down": 0.2,
        "spread_z": 0.1,
        "overshoot": 0.2,
        "compression": 0.1,
        "intensity_grad": 0.1,
        "theta_band": 1.0,
        "beta": (1.0, 2.0),
        "kappa": 0.5,
        "omega": (0.0, 1.0, 1.0, 1.0),
    }
    res = band_conditioned_hazard_moe_node(data)
    diff = 0.6 - 0.2
    alpha_mom = 1.0 * (2.0 * diff / (1 + abs(2.0 * diff))) * math.exp(-0.5 * 0.1)
    gate = 1 / (1 + math.exp(-(0.0 + 0.2 + 0.1 + 0.1)))
    expected_alpha = gate * alpha_mom
    assert res["alpha_mom"] == pytest.approx(alpha_mom)
    assert res["gate"] == pytest.approx(gate)
    assert res["alpha"] == pytest.approx(expected_alpha)


def test_band_conditioned_hazard_moe_reversion():
    data = {
        "pbx": 0.2,
        "hazard_up": 0.4,
        "hazard_down": 0.1,
        "overshoot": 0.1,
        "theta_band": 1.0,
        "theta_in": 0.5,
    }
    res = band_conditioned_hazard_moe_node(data)
    inner = 1.0 * (0.5 - abs(0.2))
    alpha_rev = -1.0 * math.log1p(math.exp(inner))
    gate = 1 / (1 + math.exp(-0.1))
    expected_alpha = (1 - gate) * alpha_rev
    assert res["alpha_rev"] == pytest.approx(alpha_rev)
    assert res["alpha"] == pytest.approx(expected_alpha)
