import math
import pytest

from qmtl.transforms.resiliency import impact, resiliency_alpha


def test_impact_basic():
    assert impact(4.0, 16.0, 2.0, 1.0) == pytest.approx(0.25)


def test_impact_guards_zero():
    assert impact(1.0, 0.0, 1.0, 1.0) == 0.0
    assert impact(1.0, 1.0, 0.0, 1.0) == 0.0


def test_resiliency_alpha():
    imp = impact(4.0, 16.0, 2.0, 1.0)
    alpha = resiliency_alpha(imp, 0.2, 0.1, 2.0)
    expected = math.tanh(2.0 * imp * 0.2) * 0.1
    assert alpha == pytest.approx(expected)
