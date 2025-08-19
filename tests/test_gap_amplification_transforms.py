import pytest

from qmtl.transforms.gap_amplification import (
    gap_over_depth_sum,
    hazard_probability,
    gati_side,
)


def test_gap_over_depth_sum():
    gas = gap_over_depth_sum([1.0, 2.0], [10.0, 20.0], lam=0.0)
    assert gas == pytest.approx(1.0 / 10.0 + 2.0 / 20.0)


def test_hazard_probability():
    hazard = hazard_probability(0.0, 0.0, 0.0, 0.0, 0.0)
    assert hazard == pytest.approx(0.5)


def test_gati_side():
    gas = 0.3
    hazard = 0.2
    assert gati_side(gas, hazard) == pytest.approx(gas * hazard)
