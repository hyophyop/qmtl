import pytest
import math

from qmtl.transforms.order_book_clustering_collapse import (
    hazard_probability,
    direction_gating,
    execution_cost,
)


def test_hazard_probability():
    z = {
        "C": 0.0,
        "Cliff": 0.0,
        "Gap": 0.0,
        "CH": 0.0,
        "RL": 0.0,
        "Shield": 0.0,
        "QDT_inv": 0.0,
        "Pers": 0.0,
    }
    beta = (0.0,) * 9
    hazard = hazard_probability(z, beta)
    assert hazard == pytest.approx(0.5)


def test_direction_gating():
    z = {"OFI": 1.0, "MicroSlope": 0.0, "AggFlow": 0.0}
    eta = (0.0, 1.0, 0.0, 0.0)
    g = direction_gating(+1, z, eta)
    expected = math.tanh(1.0)
    assert g == pytest.approx(expected)


def test_execution_cost():
    cost = execution_cost(0.2, 0.1, 0.05)
    assert cost == pytest.approx(0.2 / 2 + 0.1 + 0.05)
