import pytest

from qmtl.transforms.resiliency import impact, resiliency_alpha


def test_impact_basic():
    imp = impact(10.0, 5.0, 2.0, 1.0)
    assert imp == pytest.approx(1.0)


def test_resiliency_alpha_basic():
    imp = 1.0
    res = resiliency_alpha(imp, 0.2, 0.3, 1.0)
    assert res == pytest.approx(1.0 - 0.2 + 0.3)

