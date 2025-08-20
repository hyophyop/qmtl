import math
import pytest

from qmtl.transforms.tactical_liquidity_bifurcation import (
    bifurcation_hazard,
    direction_signal,
    tlbh_alpha,
)
from qmtl.transforms.order_book_clustering_collapse import execution_cost


def test_bifurcation_hazard_baseline():
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
    h = bifurcation_hazard(z, beta)
    assert h == pytest.approx(0.5)


def test_direction_signal_baseline():
    z = {"OFI": 0.0, "MicroSlope": 0.0, "AggFlow": 0.0}
    eta = (0.0,) * 4
    g = direction_signal(+1, z, eta)
    assert g == pytest.approx(0.0)


def test_tlbh_alpha_combination():
    h = 0.8
    g = 0.5
    pi = 0.9
    cost = execution_cost(1.0, 0.01, 0.02)
    alpha = tlbh_alpha(h, g, pi, cost, gamma=2.0, tau=0.7, phi=1.0)
    expected = max(h**2 - 0.7, 0.0) * g * pi * math.exp(-cost)
    assert alpha == pytest.approx(expected)
