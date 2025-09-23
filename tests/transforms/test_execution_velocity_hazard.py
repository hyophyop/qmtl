import math

from qmtl.runtime.transforms.execution_velocity_hazard import (
    edvh_hazard,
    expected_jump,
    execution_velocity_hazard,
)


def test_edvh_hazard_matches_manual():
    eta = [0.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0]
    x = 0.5
    t = 0.2
    depth = 1.0
    out = edvh_hazard(x, t, depth, 0.0, 0.0, 0.0, eta)
    expected = 1.0 / (1.0 + math.exp(-(eta[1]*x + eta[2]*t - math.log(depth + 1e-9))))
    assert math.isclose(out, expected)


def test_expected_jump_computation():
    gaps = [0.5, 1.0]
    depths = [0.2, 1.2]
    out = expected_jump(gaps, depths, q_quantile=1.0)
    pj = [1.0 if d <= 1.0 else 0.5 for d in depths[1:]]
    expected = gaps[0] + 0.5 * sum(p * g for p, g in zip(pj, gaps[1:]))
    assert math.isclose(out, expected)


def test_execution_velocity_hazard_combines_terms():
    eta = [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    gaps = [0.5]
    depths = [0.3]
    out = execution_velocity_hazard(0.2, 0.0, 1.0, 0.0, 0.0, 0.0, gaps, depths, eta, 1.0)
    h = edvh_hazard(0.2, 0.0, 1.0, 0.0, 0.0, 0.0, eta)
    j = expected_jump(gaps, depths, 1.0)
    assert math.isclose(out, h * j)
