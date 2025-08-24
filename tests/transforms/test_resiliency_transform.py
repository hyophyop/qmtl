from qmtl.transforms import impact, resiliency_alpha
import math


def test_impact_non_linear_scaling():
    val = impact(100.0, 25.0, 4.0, 2.0)
    assert val == 0.125


def test_resiliency_alpha_tanh():
    imp = impact(400.0, 25.0, 2.0, 1.0)
    result = resiliency_alpha(imp, 3.0, 0.5, 10.0)
    expected = math.tanh(10.0 * imp * 3.0) * 0.5
    assert result == expected
