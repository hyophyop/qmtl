import math

from qmtl.transforms.impact import impact


def test_impact_computes_expected_value():
    assert impact(100.0, 400.0, 10.0, 1.0) == math.sqrt(100.0 / 400.0) / 10.0**1.0


def test_impact_handles_invalid_inputs():
    assert impact(100.0, 0.0, 10.0, 1.0) == 0.0
    assert impact(100.0, 400.0, 0.0, 1.0) == 0.0
