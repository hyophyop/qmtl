import pytest
from collections import deque
import sys
from pathlib import Path
import math

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "qmtl"))

from strategies.nodes.indicators.acceptable_price_band import (
    acceptable_price_band_node,
)
from qmtl.common import FourDimCache


def test_band_calculation():
    cache = FourDimCache()
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
    result = acceptable_price_band_node(data, cache)
    assert result["band_upper"] == pytest.approx(109.937, rel=1e-3)
    assert result["pbx"] == pytest.approx(1.012, rel=1e-3)


def test_nonlinear_response_signs():
    cache_o = FourDimCache()
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
        },
        cache_o,
    )
    cache_i = FourDimCache()
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
        },
        cache_i,
    )
    assert outside["alpha"] > 0
    assert inside["alpha"] < 0


def test_volume_surprise_normalization():
    cache = FourDimCache()
    result = acceptable_price_band_node(
        {
            "price": 100.0,
            "volume": 120.0,
            "volume_hat": 100.0,
            "volume_std": 10.0,
        },
        cache,
    )
    assert result["volume_surprise"] == pytest.approx(2.0)


def test_cache_retrieval_and_window():
    cache = FourDimCache()
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
            "cache_window": 2,
        },
        cache,
    )

    cached_mu = sum(first["cache"].get("t0", "mid", 100, "mu")) / len(
        first["cache"].get("t0", "mid", 100, "mu")
    )
    cached_sigma = sum(first["cache"].get("t0", "mid", 100, "sigma")) / len(
        first["cache"].get("t0", "mid", 100, "sigma")
    )
    cached_vhat = sum(first["cache"].get("t0", "mid", 100, "volume_hat")) / len(
        first["cache"].get("t0", "mid", 100, "volume_hat")
    )
    cached_vstd = sum(first["cache"].get("t0", "mid", 100, "volume_std")) / len(
        first["cache"].get("t0", "mid", 100, "volume_std")
    )

    manual_cache = FourDimCache()
    for feature in ("mu", "sigma", "volume_hat", "volume_std"):
        values = first["cache"].get("t0", "mid", 100, feature)
        manual_cache.set("t0", "mid", 100, feature, deque(values, maxlen=values.maxlen))

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
            "cache_window": 2,
        },
        manual_cache,
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
            "cache_window": 2,
        },
        first["cache"],
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
            "cache_window": 2,
        },
        auto["cache"],
    )
    assert ( 
        len(third["cache"].get("t0", "mid", 100, "mu")) == 2
    )


def test_extended_gating_features():
    cache = FourDimCache()
    # seed previous pbx
    acceptable_price_band_node(
        {
            "price": 100.0,
            "volume": 100.0,
            "volume_hat": 100.0,
            "volume_std": 10.0,
            "lambda_mu": 0.5,
            "lambda_sigma": 0.5,
            "k": 1.0,
            "time": "t0",
            "price_level": 100,
        },
        cache,
    )

    result = acceptable_price_band_node(
        {
            "price": 101.0,
            "volume": 100.0,
            "volume_hat": 100.0,
            "volume_std": 10.0,
            "lambda_mu": 0.5,
            "lambda_sigma": 0.5,
            "k": 1.0,
            "time": "t0",
            "price_level": 100,
            "bid_ofi": 4.0,
            "ask_ofi": 1.0,
            "sigma_short": 1.0,
            "sigma_long": 0.5,
            "iv": 0.3,
            "hv": 0.2,
            "coef_dpbx": 1.0,
            "coef_ofi_gap": 1.0,
            "coef_vol_squeeze": 1.0,
            "coef_iv_hv": 1.0,
            "coef_overshoot": 0.0,
            "coef_volume_surprise": 0.0,
        },
        cache,
    )

    dpbx = result["pbx_delta"]
    ofi_gap = result["ofi_gap"]
    vol_sq = result["volatility_squeeze"]
    ivhv = result["iv_hv_spread"]
    gate_expected = 1.0 / (1.0 + math.exp(-(dpbx + ofi_gap + vol_sq + ivhv)))

    sigma = result["sigma"]
    pbx = result["pbx"]
    resid = pbx * 1.0 * sigma
    alpha_mom = math.log1p(math.exp(0.0))
    inner = (1.0 * sigma - abs(resid)) / sigma if sigma else 0.0
    alpha_rev = -math.log1p(math.exp(inner))
    alpha_expected = gate_expected * alpha_mom + (1.0 - gate_expected) * alpha_rev

    assert result["alpha"] == pytest.approx(alpha_expected)

