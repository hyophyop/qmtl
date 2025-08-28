import math
import pytest

from qmtl.transforms.execution_diffusion_contraction import (
    concentration_scores,
    depth_wedge,
    hazard_probability,
    path_resistance,
    expected_jump,
    edch_side,
)


def test_concentration_scores():
    e, h, f = concentration_scores([1.0, 1.0, 2.0], [1.0, 1.0, 1.0], bins=2)
    assert e == pytest.approx(0.6365141682929341)
    assert h == pytest.approx(0.5555555555551852)
    assert f == pytest.approx(0.5)


def test_path_resistance_and_depth_wedge():
    assert path_resistance([1.0, 1.0]) == pytest.approx(-math.log(2.0))
    wedge = depth_wedge([1.0, 1.0], [2.0, 1.0])
    assert wedge == pytest.approx((2.0 - 3.0) / (2.0 + 3.0))


def test_hazard_probability():
    prob = hazard_probability([0.0, 0.0], [0.0, 0.0, 0.0])
    assert prob == pytest.approx(0.5)


def test_expected_jump_and_edch_side():
    jump = expected_jump([1.0, 2.0], [0.5, 1.5], q_quantile=1.0, zeta=0.5)
    prob = 0.5
    edch = edch_side(prob, jump)
    assert edch == pytest.approx(prob * jump)
