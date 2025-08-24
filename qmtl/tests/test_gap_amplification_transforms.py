import pytest

from qmtl.transforms.gap_amplification import (
    gap_over_depth_sum,
    hazard_probability,
    gati_side,
    jump_expectation,
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
    jump = 1.5
    assert gati_side(gas, hazard, jump) == pytest.approx(gas * hazard * jump)


def test_jump_expectation():
    gaps = [0.5, 1.0, 1.5]
    depths = [10.0, 5.0, 5.0]
    expect = jump_expectation(gaps, depths, zeta=0.1)
    assert expect == pytest.approx(0.6)
