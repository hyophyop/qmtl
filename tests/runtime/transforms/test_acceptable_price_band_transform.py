import pytest

from qmtl.runtime.transforms.acceptable_price_band import (
    estimate_band,
    overshoot,
    volume_surprise,
)


def test_estimate_band():
    res = estimate_band(
        price=110.0,
        mu_prev=100.0,
        sigma_prev=2.0,
        lambda_mu=0.5,
        lambda_sigma=0.1,
        k=2.0,
    )
    assert res["band_upper"] == pytest.approx(109.937, rel=1e-3)
    assert res["pbx"] == pytest.approx(1.012, rel=1e-3)


def test_overshoot():
    assert overshoot(resid=5.0, sigma=2.0, k=1.0) == pytest.approx(1.5)


def test_volume_surprise():
    assert volume_surprise(120.0, 100.0, 10.0) == pytest.approx(2.0)
