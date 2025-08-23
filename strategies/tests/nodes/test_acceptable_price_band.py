import pytest
from collections import deque
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "qmtl"))

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


def test_cache_retrieval_and_window():
    cache = {}
    first = acceptable_price_band_node(
        {
            "price": 100.0,
            "volume": 100.0,
            "volume_hat": 90.0,
            "volume_std": 5.0,
            "mu_prev": 100.0,
            "sigma_prev": 1.0,
            "lambda_mu": 0.5,
            "lambda_sigma": 0.5,
            "k": 1.0,
            "time": "t0",
            "price_level": 100,
            "cache": cache,
            "cache_window": 2,
        }
    )

    key_mu = ("t0", 100, "mu")
    cached_mu = sum(first["cache"][key_mu]) / len(first["cache"][key_mu])
    key_sigma = ("t0", 100, "sigma")
    cached_sigma = sum(first["cache"][key_sigma]) / len(first["cache"][key_sigma])
    key_vhat = ("t0", 100, "volume_hat")
    cached_vhat = sum(first["cache"][key_vhat]) / len(first["cache"][key_vhat])
    key_vstd = ("t0", 100, "volume_std")
    cached_vstd = sum(first["cache"][key_vstd]) / len(first["cache"][key_vstd])

    manual_cache = {k: deque(v, maxlen=v.maxlen) for k, v in first["cache"].items()}
    manual = acceptable_price_band_node(
        {
            "price": 101.0,
            "volume": 110.0,
            "mu_prev": cached_mu,
            "sigma_prev": cached_sigma,
            "volume_hat": cached_vhat,
            "volume_std": cached_vstd,
            "lambda_mu": 0.5,
            "lambda_sigma": 0.5,
            "k": 1.0,
            "time": "t0",
            "price_level": 100,
            "cache": manual_cache,
            "cache_window": 2,
        }
    )

    auto = acceptable_price_band_node(
        {
            "price": 101.0,
            "volume": 110.0,
            "lambda_mu": 0.5,
            "lambda_sigma": 0.5,
            "k": 1.0,
            "time": "t0",
            "price_level": 100,
            "cache": first["cache"],
            "cache_window": 2,
        }
    )

    for key in (
        "mu",
        "sigma",
        "band_upper",
        "band_lower",
        "pbx",
        "alpha",
        "volume_surprise",
    ):
        assert auto[key] == pytest.approx(manual[key])

    # window enforcement
    third = acceptable_price_band_node(
        {
            "price": 102.0,
            "volume": 120.0,
            "lambda_mu": 0.5,
            "lambda_sigma": 0.5,
            "k": 1.0,
            "time": "t0",
            "price_level": 100,
            "cache": auto["cache"],
            "cache_window": 2,
        }
    )
    assert len(third["cache"][key_mu]) == 2

