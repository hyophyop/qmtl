import math

import pytest

from qmtl.services.worldservice.validation_metrics import augment_advanced_metrics


def test_augment_advanced_metrics_filters_non_finite_inputs():
    metrics = {"returns": {"sharpe": 1.0}}
    returns = [0.01, math.nan, -0.02, math.inf, -0.03, -math.inf] * 25

    derived = augment_advanced_metrics(metrics, returns=returns)

    assert math.isfinite(derived["returns"]["var_p01"])
    assert math.isfinite(derived["returns"]["es_p01"])
    assert derived["returns"]["max_time_under_water_days"] is not None

    coverage = derived["sample"]["regime_coverage"]
    assert set(coverage.keys()) == {"low_vol", "mid_vol", "high_vol"}
    assert coverage["low_vol"] + coverage["mid_vol"] + coverage["high_vol"] == pytest.approx(1.0)
