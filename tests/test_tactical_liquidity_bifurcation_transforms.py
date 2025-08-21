import math
import pytest

from qmtl.transforms.tactical_liquidity_bifurcation import (
    bifurcation_hazard,
    direction_signal,
    tlbh_alpha,
)


def test_bifurcation_hazard_basic():
    z = {
        "SkewDot": 0.0,
        "CancelDot": 0.0,
        "Gap": 0.0,
        "Cliff": 0.0,
        "Shield": 0.0,
        "QDT_inv": 0.0,
        "RequoteLag": 0.0,
    }
    beta = (0.0,) * 8
    assert bifurcation_hazard(z, beta) == pytest.approx(0.5)


def test_direction_signal_and_alpha():
    z = {"OFI": 0.2, "MicroSlope": 0.1, "AggFlow": 0.3}
    eta = (0.0, 1.0, 1.0, 1.0)
    g = direction_signal(+1, z, eta)
    expected_g = math.tanh(0.0 + 1.0*0.2 + 1.0*0.1 + 1.0*1.0*0.3)
    assert g == pytest.approx(expected_g)

    alpha = tlbh_alpha(0.8, g, 0.9, 0.1, 2.0, 0.7, 1.0)
    expected_alpha = max(0.8**2 - 0.7, 0.0) * g * 0.9 * math.exp(-0.1)
    assert alpha == pytest.approx(expected_alpha)
