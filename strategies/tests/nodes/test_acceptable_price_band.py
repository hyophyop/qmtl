import pytest

from strategies.nodes.indicators.acceptable_price_band import (
    acceptable_price_band_node,
)


def test_band_calculation():
    data = {
        "price": 110.0,
        "volume": 150.0,
        "volume_hat": 100.0,
        "volume_std": 10.0,
        "mu_prev": 100.0,
        "sigma_prev": 2.0,
        "lambda_mu": 0.5,
        "lambda_sigma": 0.1,
        "k": 2.0,
    }
    result = acceptable_price_band_node(data)
    assert result["band_upper"] == pytest.approx(109.937, rel=1e-3)
    assert result["pbx"] == pytest.approx(1.012, rel=1e-3)


def test_nonlinear_response_signs():
    outside = acceptable_price_band_node(
        {
            "price": 110.0,
            "volume": 150.0,
            "volume_hat": 100.0,
            "volume_std": 10.0,
            "mu_prev": 100.0,
            "sigma_prev": 2.0,
            "lambda_mu": 0.5,
            "lambda_sigma": 0.1,
            "k": 2.0,
        }
    )
    inside = acceptable_price_band_node(
        {
            "price": 102.0,
            "volume": 100.0,
            "volume_hat": 100.0,
            "volume_std": 10.0,
            "mu_prev": 100.0,
            "sigma_prev": 2.0,
            "lambda_mu": 0.5,
            "lambda_sigma": 0.1,
            "k": 2.0,
        }
    )
    assert outside["alpha"] > 0
    assert inside["alpha"] < 0


def test_volume_surprise_normalization():
    result = acceptable_price_band_node(
        {
            "price": 100.0,
            "volume": 120.0,
            "volume_hat": 100.0,
            "volume_std": 10.0,
        }
    )
    assert result["volume_surprise"] == pytest.approx(2.0)

