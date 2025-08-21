import pytest

from qmtl.transforms.execution_diffusion_contraction import (
    concentration_scores,
    hazard_probability,
    expected_jump,
    edch_side,
)


def test_concentration_scores():
    e, h, f = concentration_scores([1.0, 1.0, 2.0], [1.0, 1.0, 1.0], bins=2)
    assert e >= 0
    assert h >= 0
    assert f >= 0


def test_hazard_probability():
    prob = hazard_probability([0.0, 0.0], [0.0, 0.0, 0.0])
    assert prob == pytest.approx(0.5)


def test_expected_jump_and_edch_side():
    jump = expected_jump([1.0, 2.0], [0.5, 1.5], q_quantile=1.0, zeta=0.5)
    prob = 0.5
    edch = edch_side(prob, jump)
    assert edch == pytest.approx(prob * jump)
